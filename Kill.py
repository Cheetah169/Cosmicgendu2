#!/usr/bin/env python3
"""
Advanced Dork Parser with Selenium
Author: @Cheetax1
Description: Multi-engine dork parser with proxy support, retry system, and optimization
"""

import os
import sys
import time
import random
import threading
import requests
import platform
from urllib.parse import urlparse, urljoin
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from datetime import datetime, timedelta


class DorkParser:
    def __init__(self):
        self.setup_logging()
        self.stats = {
            'total_dorks': 0,
            'checked_dorks': 0,
            'urls_parsed': 0,
            'error_dorks': 0,
            'retry_dorks': 0,
            'working_engines': [],
            'start_time': time.time()
        }
        
        self.search_engines = {
            'google': 'https://www.google.com/search?q={}&start={}',
            'bing': 'https://www.bing.com/search?q={}&first={}',
            'duckduckgo': 'https://duckduckgo.com/?q={}&s={}',
            'yahoo': 'https://search.yahoo.com/search?p={}&b={}'
        }
        
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0"
        ]
        
        self.proxies = []
        self.proxy_type = None
        self.is_rotating = False
        self.results_file = "results.txt"
        self.errors_file = "errors.txt"
        self.retries_file = "retries.txt"
        self.lock = threading.Lock()
        
    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('dork_parser.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def detect_os(self):
        """Detect operating system"""
        return platform.system().lower()
        
    def setup_chrome_driver(self, proxy=None):
        """Setup Chrome driver with anti-detection and proxy support"""
        try:
            chrome_options = Options()
            
            # Headless mode
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            
            # Anti-detection
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Random user agent
            user_agent = random.choice(self.user_agents)
            chrome_options.add_argument(f'--user-agent={user_agent}')
            
            # Proxy configuration
            if proxy:
                if len(proxy.split(':')) == 2:
                    # ip:port format
                    chrome_options.add_argument(f'--proxy-server=http://{proxy}')
                elif len(proxy.split(':')) == 4:
                    # ip:port:username:password format
                    ip, port, username, password = proxy.split(':')
                    chrome_options.add_argument(f'--proxy-server=http://{ip}:{port}')
                    # Note: Chrome doesn't support auth via command line, would need extension
                    
            # Setup ChromeDriver path with fix for Linux path issue
            try:
                # Get the driver path
                driver_path = ChromeDriverManager().install()
                
                # Fix for Linux path issue - ensure we get the correct executable
                if os.path.exists(driver_path):
                    # Check if it's a directory (common issue)
                    if os.path.isdir(driver_path):
                        # Look for chromedriver executable in the directory
                        possible_paths = [
                            os.path.join(driver_path, 'chromedriver'),
                            os.path.join(driver_path, 'chromedriver-linux64', 'chromedriver'),
                        ]
                        for path in possible_paths:
                            if os.path.exists(path) and os.access(path, os.X_OK):
                                driver_path = path
                                break
                    
                    # Make sure it's executable
                    if not os.access(driver_path, os.X_OK):
                        os.chmod(driver_path, 0o755)
                        
                self.logger.info(f"Using ChromeDriver at: {driver_path}")
                service = Service(driver_path)
                
            except Exception as e:
                self.logger.error(f"Failed to setup ChromeDriver: {e}")
                # Fallback: try to use system chromedriver
                try:
                    service = Service('/usr/bin/chromedriver')
                except:
                    return None
                
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Execute script to remove webdriver property
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            return driver
            
        except Exception as e:
            self.logger.error(f"Error setting up Chrome driver: {e}")
            return None
            
    def validate_proxy(self, proxy):
        """Validate proxy connection"""
        try:
            if len(proxy.split(':')) == 2:
                proxy_dict = {'http': f'http://{proxy}', 'https': f'http://{proxy}'}
            elif len(proxy.split(':')) == 4:
                ip, port, username, password = proxy.split(':')
                proxy_dict = {
                    'http': f'http://{username}:{password}@{ip}:{port}',
                    'https': f'http://{username}:{password}@{ip}:{port}'
                }
            else:
                return False
                
            response = requests.get('http://httpbin.org/ip', proxies=proxy_dict, timeout=10)
            return response.status_code == 200
        except:
            return False
            
    def load_proxies(self):
        """Load and validate proxies"""
        print("\n=== PROXY SETUP ===")
        proxy_choice = input("Do you want to use proxies? (y/n): ").lower()
        
        if proxy_choice != 'y':
            return
            
        proxy_input = input("Enter proxy file path or single proxy (ip:port or ip:port:user:pass): ")
        
        if os.path.exists(proxy_input):
            # Load from file
            with open(proxy_input, 'r') as f:
                self.proxies = [line.strip() for line in f if line.strip()]
        else:
            # Single proxy
            self.proxies = [proxy_input]
            
        # Determine if rotating
        rotate_choice = input("Is this a rotating proxy? (y/n): ").lower()
        self.is_rotating = rotate_choice == 'y'
        
        # Validate non-rotating proxies
        if not self.is_rotating:
            print("Validating proxies...")
            valid_proxies = []
            for proxy in self.proxies:
                if self.validate_proxy(proxy):
                    valid_proxies.append(proxy)
                    print(f"✓ Valid: {proxy}")
                else:
                    print(f"✗ Invalid: {proxy}")
            self.proxies = valid_proxies
            
        print(f"Loaded {len(self.proxies)} proxies")
        
    def load_dorks(self):
        """Load dorks from user input or file"""
        print("\n=== DORK INPUT ===")
        choice = input("1. Enter single dork\n2. Load from dorks.txt\nChoice (1/2): ")
        
        if choice == '1':
            dork = input("Enter your dork: ")
            return [dork]
        else:
            dorks_file = input("Enter dorks file path (default: dorks.txt): ") or "dorks.txt"
            if os.path.exists(dorks_file):
                with open(dorks_file, 'r') as f:
                    dorks = [line.strip() for line in f if line.strip()]
                print(f"Loaded {len(dorks)} dorks from {dorks_file}")
                return dorks
            else:
                print(f"File {dorks_file} not found!")
                return []
                
    def get_search_results(self, driver, dork, engine, page=0):
        """Get search results for a dork from specified engine"""
        try:
            if engine == 'google':
                start = page * 10
                url = self.search_engines[engine].format(dork, start)
            elif engine == 'bing':
                first = page * 10 + 1
                url = self.search_engines[engine].format(dork, first)
            elif engine == 'duckduckgo':
                url = self.search_engines[engine].format(dork, page * 10)
            elif engine == 'yahoo':
                b = page * 10 + 1
                url = self.search_engines[engine].format(dork, b)
                
            driver.get(url)
            time.sleep(random.uniform(1, 3))  # Random delay
            
            # Parse results based on engine
            links = []
            if engine == 'google':
                elements = driver.find_elements(By.CSS_SELECTOR, 'div.g a[href]')
                for elem in elements:
                    href = elem.get_attribute('href')
                    if href and href.startswith('http') and 'google.com' not in href:
                        links.append(href)
                        
            elif engine == 'bing':
                elements = driver.find_elements(By.CSS_SELECTOR, 'li.b_algo h2 a[href]')
                for elem in elements:
                    href = elem.get_attribute('href')
                    if href and href.startswith('http'):
                        links.append(href)
                        
            elif engine == 'duckduckgo':
                elements = driver.find_elements(By.CSS_SELECTOR, 'a[data-testid="result-title-a"]')
                for elem in elements:
                    href = elem.get_attribute('href')
                    if href and href.startswith('http'):
                        links.append(href)
                        
            elif engine == 'yahoo':
                elements = driver.find_elements(By.CSS_SELECTOR, 'div.algo h3 a[href]')
                for elem in elements:
                    href = elem.get_attribute('href')
                    if href and href.startswith('http'):
                        links.append(href)
                        
            return links
            
        except Exception as e:
            self.logger.error(f"Error getting results from {engine}: {e}")
            return []
            
    def process_dork(self, dork, pages, max_retries=3):
        """Process a single dork with retry mechanism"""
        retries = 0
        all_links = []
        
        while retries < max_retries:
            try:
                # Get proxy if available
                proxy = None
                if self.proxies:
                    proxy = random.choice(self.proxies)
                    
                # Setup driver
                driver = self.setup_chrome_driver(proxy)
                if not driver:
                    retries += 1
                    continue
                    
                # Try each search engine
                engines_tried = []
                for engine in self.search_engines.keys():
                    try:
                        if engine not in self.stats['working_engines']:
                            self.stats['working_engines'].append(engine)
                            
                        for page in range(pages):
                            links = self.get_search_results(driver, dork, engine, page)
                            all_links.extend(links)
                            
                            with self.lock:
                                self.stats['urls_parsed'] += len(links)
                                
                        engines_tried.append(engine)
                        break  # Success, exit engine loop
                        
                    except Exception as e:
                        self.logger.error(f"Engine {engine} failed for dork '{dork}': {e}")
                        if engine in self.stats['working_engines']:
                            self.stats['working_engines'].remove(engine)
                        continue
                        
                driver.quit()
                
                if all_links:
                    # Save results
                    with self.lock:
                        with open(self.results_file, 'a') as f:
                            f.write(f"\n# Dork: {dork}\n")
                            for link in all_links:
                                f.write(f"{link}\n")
                                
                        self.stats['checked_dorks'] += 1
                    return True
                else:
                    retries += 1
                    
            except Exception as e:
                self.logger.error(f"Error processing dork '{dork}': {e}")
                retries += 1
                if 'driver' in locals():
                    driver.quit()
                    
        # All retries failed
        with self.lock:
            self.stats['error_dorks'] += 1
            with open(self.errors_file, 'a') as f:
                f.write(f"{dork}\n")
                
        return False
        
    def display_stats(self):
        """Display live statistics"""
        while True:
            elapsed = time.time() - self.stats['start_time']
            
            if self.stats['checked_dorks'] > 0:
                avg_time_per_dork = elapsed / self.stats['checked_dorks']
                remaining_dorks = self.stats['total_dorks'] - self.stats['checked_dorks']
                estimated_time = remaining_dorks * avg_time_per_dork
                est_time_str = str(timedelta(seconds=int(estimated_time)))
            else:
                est_time_str = "Calculating..."
                
            os.system('cls' if os.name == 'nt' else 'clear')
            print("="*60)
            print("             DORK PARSER STATISTICS")
            print("="*60)
            print(f"Total Dorks     - {self.stats['total_dorks']}")
            print(f"Checked Dorks   - {self.stats['checked_dorks']}")
            print(f"URLs Parsed     - {self.stats['urls_parsed']}")
            print(f"Error Dorks     - {self.stats['error_dorks']}")
            print(f"Retry Dorks     - {self.stats['retry_dorks']}")
            print(f"Working Engines - {', '.join(self.stats['working_engines']) if self.stats['working_engines'] else 'None'}")
            print(f"Estimated Time  - {est_time_str}")
            print(f"Owner           - @Cheetax1")
            print("="*60)
            
            time.sleep(5)
            
            if self.stats['checked_dorks'] + self.stats['error_dorks'] >= self.stats['total_dorks']:
                break
                
    def run(self):
        """Main execution function"""
        print("="*60)
        print("         ADVANCED DORK PARSER v1.0")
        print("              by @Cheetax1")
        print("="*60)
        
        # Load proxies
        self.load_proxies()
        
        # Load dorks
        dorks = self.load_dorks()
        if not dorks:
            print("No dorks loaded. Exiting...")
            return
            
        self.stats['total_dorks'] = len(dorks)
        
        # Get search parameters
        print("\n=== SEARCH CONFIGURATION ===")
        pages = int(input("How many pages to search per dork (default: 5): ") or "5")
        threads = int(input("How many dorks to run simultaneously (default: 3): ") or "3")
        
        print(f"\nStarting search for {len(dorks)} dorks with {pages} pages each...")
        print("Press Ctrl+C to stop\n")
        
        # Clear previous results
        for file in [self.results_file, self.errors_file, self.retries_file]:
            if os.path.exists(file):
                os.remove(file)
                
        # Start stats display thread
        stats_thread = threading.Thread(target=self.display_stats, daemon=True)
        stats_thread.start()
        
        # Process dorks with ThreadPoolExecutor
        try:
            with ThreadPoolExecutor(max_workers=threads) as executor:
                future_to_dork = {
                    executor.submit(self.process_dork, dork, pages): dork 
                    for dork in dorks
                }
                
                for future in as_completed(future_to_dork):
                    dork = future_to_dork[future]
                    try:
                        result = future.result()
                    except Exception as e:
                        self.logger.error(f"Dork '{dork}' generated an exception: {e}")
                        
        except KeyboardInterrupt:
            print("\n\nStopping parser...")
            
        # Final stats
        print("\n" + "="*60)
        print("                FINAL RESULTS")
        print("="*60)
        print(f"Total Dorks Processed: {self.stats['checked_dorks']}")
        print(f"Total URLs Found: {self.stats['urls_parsed']}")
        print(f"Failed Dorks: {self.stats['error_dorks']}")
        print(f"Results saved to: {self.results_file}")
        print(f"Errors saved to: {self.errors_file}")
        print("="*60)


if __name__ == "__main__":
    try:
        parser = DorkParser()
        parser.run()
    except KeyboardInterrupt:
        print("\nParser stopped by user.")
    except Exception as e:
        print(f"Critical error: {e}")
        logging.error(f"Critical error: {e}")
