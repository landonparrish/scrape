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
        
        # Enhanced headers with more browser-like behavior
        headers = {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'TE': 'trailers'
        }
        
        # Add domain-specific headers
        if 'lever.co' in domain:
            headers.update({
                'Origin': 'https://jobs.lever.co',
                'Referer': 'https://jobs.lever.co/',
                'Host': 'jobs.lever.co'
            })
        elif 'greenhouse.io' in domain:
            headers.update({
                'Origin': 'https://boards.greenhouse.io',
                'Referer': 'https://boards.greenhouse.io/',
                'Host': 'boards.greenhouse.io'
            })
        
        config = {
            'headers': headers,
            'verify': False,  # Allow unverified HTTPS
            'allow_redirects': True,
            'timeout': 30
        }
        
        if self.should_use_proxy(url):
            proxies = self.get_proxies()
            if proxies:
                proxy = random.choice(proxies)
                if not proxy.startswith(('http://', 'https://')):
                    proxy = f'http://{proxy}'
                config['proxies'] = {
                    'http': proxy,
                    'https': proxy
                }
                logging.info(f"Using proxy for {domain}: {proxy}")
        
        return config

    def _get_random_user_agent(self) -> str:
        return random.choice(self.user_agents)

    def _test_proxy(self, proxy: str, timeout: int = 5) -> bool:
        """Test if a proxy is working by trying to connect to a test URL."""
        try:
            # Format proxy correctly
            if not proxy.startswith(('http://', 'https://')):
                proxy = f'http://{proxy}'

            proxies = {
                'http': proxy,
                'https': proxy
            }
            
            headers = {
                'User-Agent': self._get_random_user_agent(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # Test multiple URLs to ensure proxy works with different sites
            test_urls = [
                'http://example.com',
                'https://httpbin.org/ip',
                'https://api.ipify.org?format=json'
            ]
            
            for url in test_urls:
                try:
                    response = requests.get(
                        url,
                        proxies=proxies,
                        headers=headers,
                        timeout=timeout,
                        verify=False
                    )
                    
                    if response.status_code == 200:
                        # Additional validation for IP check services
                        if 'ipify.org' in url or 'httpbin.org' in url:
                            try:
                                ip_data = response.json()
                                if ip_data.get('ip') or ip_data.get('origin'):
                                    return True
                            except:
                                continue
                        else:
                            return True
                except:
                    continue
                    
            return False
            
        except Exception as e:
            logging.debug(f"Proxy {proxy} failed: {str(e)}")
            return False

    def get_proxies(self, force_refresh: bool = False, min_proxies: int = 5) -> List[str]:
        """Get a list of working proxies, using cache if available and not expired."""
        current_time = time.time()
        
        # Return cached proxies if they're still fresh and we have enough
        if not force_refresh and len(self.cached_proxies) >= min_proxies and \
           (current_time - self.last_fetch_time) < self.min_fetch_interval:
            return self.cached_proxies

        proxies = []
        
        # Try multiple proxy sources
        proxy_sources = [
            "https://free-proxy-list.net/",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt"
        ]
        
        headers = {'User-Agent': self._get_random_user_agent()}
        
        for source in proxy_sources:
            try:
                response = requests.get(source, headers=headers, timeout=10)
                
                if source.endswith('.txt'):
                    # Parse plain text proxy list
                    for line in response.text.splitlines():
                        if ':' in line:
                            proxies.append(line.strip())
                else:
                    # Parse HTML table
                    soup = BeautifulSoup(response.content, "html.parser")
                    table = soup.find("table", attrs={"class": "table table-striped table-bordered"})
                    
                    if table:
                        rows = table.find_all("tr")[1:]
                        for row in rows:
                            cols = row.find_all("td")
                            if len(cols) >= 8:
                                ip = cols[0].text.strip()
                                port = cols[1].text.strip()
                                https = cols[6].text.strip()
                                google = cols[5].text.strip()
                                
                                if https.lower() == 'yes' and google.lower() == 'yes':
                                    proxies.append(f"{ip}:{port}")
                
            except Exception as e:
                logging.warning(f"Failed to fetch proxies from {source}: {str(e)}")
                continue

        # Shuffle and test proxies
        random.shuffle(proxies)
        working_proxies = []
        max_to_test = min(50, len(proxies))  # Test more proxies
        
        logging.info(f"Testing {max_to_test} proxies...")
        
        for proxy in proxies[:max_to_test]:
            if self._test_proxy(proxy):
                working_proxies.append(proxy)
                logging.info(f"Found working proxy: {proxy}")
                
                if len(working_proxies) >= min_proxies:
                    break

        if working_proxies:
            self.cached_proxies = working_proxies
            self.last_fetch_time = current_time
            return working_proxies
        
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
