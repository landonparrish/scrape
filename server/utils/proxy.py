import requests
from bs4 import BeautifulSoup
import logging
import time
from typing import List, Optional, Dict, Union
import random
from requests.exceptions import RequestException, Timeout, ConnectionError


class ProxyFetcher:
    def __init__(self):
        self.last_fetch_time = 0
        self.min_fetch_interval = 600
        self.cached_proxies = []
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
        
        # Domain-specific configurations
        self.domain_configs = {
            'jobs.lever.co': {
                'rate_limit': 10,  # requests per minute
                'cooldown': 300,   # 5 minutes cooldown after rate limit
                'max_retries': 3
            },
            'boards.greenhouse.io': {
                'rate_limit': 15,
                'cooldown': 300,
                'max_retries': 3
            },
            'jobs.ashbyhq.com': {
                'rate_limit': 20,
                'cooldown': 240,
                'max_retries': 2
            }
        }
        
        self.domain_request_counts = {}
        self.domain_last_request = {}
        self.domain_failures = {}
        self.domain_cooldowns = {}

    def _get_domain_config(self, domain: str) -> Dict:
        """Get configuration for a specific domain, with defaults."""
        return self.domain_configs.get(domain, {
            'rate_limit': 30,
            'cooldown': 180,
            'max_retries': 2
        })

    def should_use_proxy(self, url: str) -> bool:
        """Smart proxy usage decision based on domain history."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        config = self._get_domain_config(domain)
        current_time = time.time()

        # Check if in cooldown
        if domain in self.domain_cooldowns:
            if current_time < self.domain_cooldowns[domain]:
                return True
            else:
                del self.domain_cooldowns[domain]
                self.domain_failures[domain] = 0

        # Check rate limiting
        if domain in self.domain_request_counts:
            minute_ago = current_time - 60
            # Clean old requests
            self.domain_request_counts[domain] = [
                t for t in self.domain_request_counts[domain] 
                if t > minute_ago
            ]
            
            if len(self.domain_request_counts[domain]) >= config['rate_limit']:
                return True

        # Check failure count
        return self.domain_failures.get(domain, 0) >= config['max_retries']

    def mark_request(self, url: str, success: bool, status_code: Optional[int] = None) -> None:
        """Track request results with domain-specific handling."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        config = self._get_domain_config(domain)
        current_time = time.time()

        # Track request timing
        if domain not in self.domain_request_counts:
            self.domain_request_counts[domain] = []
        self.domain_request_counts[domain].append(current_time)
        
        if success:
            # Reset failure count on success
            self.domain_failures[domain] = 0
            if domain in self.domain_cooldowns:
                del self.domain_cooldowns[domain]
        else:
            # Handle failures
            self.domain_failures[domain] = self.domain_failures.get(domain, 0) + 1
            
            # Special handling for rate limits and blocks
            if status_code in [429, 403]:
                self.domain_cooldowns[domain] = current_time + config['cooldown']
                logging.info(f"Domain {domain} in cooldown for {config['cooldown']}s due to {status_code}")
            elif self.domain_failures[domain] >= config['max_retries']:
                cooldown = config['cooldown'] // 2  # Shorter cooldown for general failures
                self.domain_cooldowns[domain] = current_time + cooldown
                logging.info(f"Domain {domain} in cooldown for {cooldown}s due to repeated failures")

    def get_request_config(self, url: str) -> Dict[str, Union[Dict, str]]:
        """Get domain-specific request configuration."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        
        headers = {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        
        # Add domain-specific headers
        if 'lever.co' in domain:
            headers['Origin'] = 'https://jobs.lever.co'
            headers['Referer'] = 'https://jobs.lever.co/'
        elif 'greenhouse.io' in domain:
            headers['Origin'] = 'https://boards.greenhouse.io'
            headers['Referer'] = 'https://boards.greenhouse.io/'
        
        config = {'headers': headers}
        
        if self.should_use_proxy(url):
            proxies = self.get_proxies()
            if proxies:
                proxy = random.choice(proxies)
                config['proxies'] = {
                    'http': f'http://{proxy}',
                    'https': f'http://{proxy}'
                }
                logging.info(f"Using proxy for {domain}: {proxy}")
        
        return config

    def _get_random_user_agent(self) -> str:
        return random.choice(self.user_agents)

    def _test_proxy(self, proxy: str, timeout: int = 5) -> bool:
        """Test if a proxy is working by trying to connect to a test URL."""
        proxies = {
            'http': f'http://{proxy}',
            'https': f'http://{proxy}'
        }
        
        headers = {'User-Agent': self._get_random_user_agent()}
        
        # Just test with one reliable URL instead of multiple
        url = 'http://example.com'  # Fastest and most reliable test URL
        try:
            response = requests.get(
                url,
                proxies=proxies,
                headers=headers,
                timeout=timeout,
                verify=False
            )
            return response.status_code == 200
        except Exception as e:
            logging.debug(f"Proxy {proxy} failed: {str(e)}")
            return False

    def get_proxies(self, force_refresh: bool = False, min_proxies: int = 5) -> List[str]:
        """Get a list of working proxies, using cache if available and not expired."""
        current_time = time.time()
        
        # Return cached proxies if they're still fresh and we have enough
        if not force_refresh and len(self.cached_proxies) >= min_proxies and \
           (current_time - self.last_fetch_time) < self.min_fetch_interval:
            logging.info(f"Using {len(self.cached_proxies)} cached proxies")
            return self.cached_proxies

        url = "https://free-proxy-list.net/"
        headers = {'User-Agent': self._get_random_user_agent()}
        proxies = []

        try:
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")
            table = soup.find("table", attrs={"class": "table table-striped table-bordered"})
            
            if not table:
                logging.error("Could not find proxy table on the website")
                return self.cached_proxies if self.cached_proxies else []

            rows = table.find_all("tr")[1:]  # Skip header row
            
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 8:
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    anonymity = cols[4].text.strip()
                    google = cols[5].text.strip().lower() == 'yes'
                    last_checked = cols[7].text.strip()
                    
                    # More lenient filtering
                    if 'mins ago' in last_checked:
                        mins = int(''.join(filter(str.isdigit, last_checked)))
                        if mins > 15:  # Increased from 5 to 15 minutes
                            continue
                    
                    # Accept all proxy types that work with Google
                    if not google:
                        continue
                    
                    proxy = f"{ip}:{port}"
                    proxies.append(proxy)

            # Shuffle all proxies
            random.shuffle(proxies)

            # Test proxies with a limit
            working_proxies = []
            max_to_test = min(20, len(proxies))  # Test at most 20 proxies
            logging.info(f"Testing up to {max_to_test} proxies...")
            
            for proxy in proxies[:max_to_test]:
                if self._test_proxy(proxy):
                    working_proxies.append(proxy)
                    logging.info(f"Found working proxy: {proxy}")
                    
                    if len(working_proxies) >= min_proxies:
                        break

            if working_proxies:
                self.cached_proxies = working_proxies
                self.last_fetch_time = current_time
                logging.info(f"Successfully found {len(working_proxies)} working proxies")
                return working_proxies
            else:
                logging.warning("No working proxies found, falling back to cached proxies")
                return self.cached_proxies if self.cached_proxies else []

        except Exception as e:
            logging.error(f"Error fetching proxies: {str(e)}")
            return self.cached_proxies if self.cached_proxies else []


# Create a global instance
proxy_fetcher = ProxyFetcher()

def get_free_proxies(force_refresh: bool = False) -> List[str]:
    """Get a list of working proxies. Maintained for backward compatibility."""
    return proxy_fetcher.get_proxies(force_refresh=force_refresh)

def get_request_config(url: str) -> Dict[str, Union[Dict, str]]:
    return proxy_fetcher.get_request_config(url)

def mark_request_result(url: str, success: bool, status_code: Optional[int] = None) -> None:
    proxy_fetcher.mark_request(url, success, status_code)
