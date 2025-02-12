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
        self.min_fetch_interval = 600  # 10 minutes, matching the site's update interval
        self.cached_proxies = []
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15'
        ]
        self.test_urls = [
            'http://example.com',  # Simple test
            'https://httpbin.org/ip',  # Returns IP info
            'https://api.ipify.org?format=json'  # Another IP service
        ]
        self.direct_connection_failures = 0
        self.max_direct_failures = 3  # Number of failures before switching to proxies
        self.using_proxies = False
        self.domain_failures: Dict[str, int] = {}  # Track failures per domain
        self.domain_cooldowns: Dict[str, float] = {}  # Track cooldown times per domain

    def _get_random_user_agent(self) -> str:
        return random.choice(self.user_agents)

    def _test_proxy(self, proxy: str, timeout: int = 10) -> bool:
        """Test if a proxy is working by trying to connect to a test URL."""
        proxies = {
            'http': f'http://{proxy}',
            'https': f'http://{proxy}'
        }
        
        headers = {'User-Agent': self._get_random_user_agent()}
        
        # Try each test URL
        for url in self.test_urls:
            try:
                response = requests.get(
                    url,
                    proxies=proxies,
                    headers=headers,
                    timeout=timeout,
                    verify=False  # Don't verify SSL to be more lenient
                )
                if response.status_code == 200:
                    logging.info(f"Proxy {proxy} working with {url}")
                    return True
            except Timeout:
                logging.debug(f"Proxy {proxy} timed out with {url}")
                continue
            except ConnectionError:
                logging.debug(f"Proxy {proxy} connection error with {url}")
                continue
            except RequestException as e:
                logging.debug(f"Proxy {proxy} failed with {url}: {str(e)}")
                continue
            except Exception as e:
                logging.debug(f"Proxy {proxy} unexpected error with {url}: {str(e)}")
                continue
        return False

    def get_proxies(self, force_refresh: bool = False, min_proxies: int = 10) -> List[str]:
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
            # Fetch proxy list with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.get(url, headers=headers, timeout=15)
                    response.raise_for_status()
                    break
                except (RequestException, Timeout) as e:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue

            soup = BeautifulSoup(response.content, "html.parser")
            table = soup.find("table", attrs={"class": "table table-striped table-bordered"})
            
            if not table:
                logging.error("Could not find proxy table on the website")
                return self.cached_proxies if self.cached_proxies else []

            # Skip header row
            rows = table.find_all("tr")[1:]
            
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 7:  # Ensure we have all needed columns
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    https = cols[6].text.strip()
                    anonymity = cols[4].text.strip()
                    
                    # Accept both HTTP and HTTPS proxies, and any anonymity level
                    proxy = f"{ip}:{port}"
                    proxies.append(proxy)

            # Shuffle proxies to avoid testing the same ones first every time
            random.shuffle(proxies)

            # Test proxies
            working_proxies = []
            logging.info(f"Testing {len(proxies)} potential proxies...")
            
            for proxy in proxies:
                if self._test_proxy(proxy):
                    working_proxies.append(proxy)
                    logging.info(f"Found working proxy: {proxy}")
                
                # If we have enough working proxies, stop testing
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

    def should_use_proxy(self, url: str) -> bool:
        """Determine if we should use a proxy for this URL based on failure history."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        
        # Check if domain is in cooldown
        if domain in self.domain_cooldowns:
            cooldown_end = self.domain_cooldowns[domain]
            if time.time() < cooldown_end:
                return True
            else:
                # Cooldown expired, reset failures
                self.domain_failures[domain] = 0
                del self.domain_cooldowns[domain]
        
        return self.domain_failures.get(domain, 0) >= self.max_direct_failures

    def mark_failure(self, url: str, status_code: Optional[int] = None) -> None:
        """Mark a failure for a domain and update cooldown if needed."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        
        # Increment failure count
        self.domain_failures[domain] = self.domain_failures.get(domain, 0) + 1
        
        # If we hit rate limit or forbidden, add longer cooldown
        if status_code in [429, 403]:
            cooldown_time = 300  # 5 minutes for rate limits
            self.domain_cooldowns[domain] = time.time() + cooldown_time
            logging.info(f"Domain {domain} in cooldown for {cooldown_time} seconds due to status {status_code}")
        
        # If we've failed too many times, add standard cooldown
        elif self.domain_failures[domain] >= self.max_direct_failures:
            cooldown_time = 60  # 1 minute for general failures
            self.domain_cooldowns[domain] = time.time() + cooldown_time
            logging.info(f"Domain {domain} in cooldown for {cooldown_time} seconds due to too many failures")

    def mark_success(self, url: str) -> None:
        """Mark a successful request for a domain."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        
        # Reset failure count on success
        if domain in self.domain_failures:
            del self.domain_failures[domain]
        if domain in self.domain_cooldowns:
            del self.domain_cooldowns[domain]


# Create a global instance
proxy_fetcher = ProxyFetcher()

def get_request_config(url: str) -> Dict[str, Union[Dict, str]]:
    """Get the appropriate request configuration (proxy and headers) for a URL."""
    headers = {
        'User-Agent': proxy_fetcher._get_random_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    config = {'headers': headers}
    
    if proxy_fetcher.should_use_proxy(url):
        # Get fresh proxies if needed
        proxies = proxy_fetcher.get_proxies()
        if proxies:
            proxy = random.choice(proxies)
            config['proxies'] = {
                'http': f'http://{proxy}',
                'https': f'http://{proxy}'
            }
            logging.info(f"Using proxy {proxy} for {url}")
    
    return config

def mark_request_result(url: str, success: bool, status_code: Optional[int] = None) -> None:
    """Mark the result of a request to help with proxy rotation decisions."""
    if success:
        proxy_fetcher.mark_success(url)
    else:
        proxy_fetcher.mark_failure(url, status_code)
