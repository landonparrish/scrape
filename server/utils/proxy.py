import requests
from bs4 import BeautifulSoup
import logging
import time
from typing import List, Optional
import random


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

    def _get_random_user_agent(self) -> str:
        return random.choice(self.user_agents)

    def _test_proxy(self, proxy: str, timeout: int = 5) -> bool:
        """Test if a proxy is working by trying to connect to a test URL."""
        test_urls = [
            'https://www.google.com',
            'https://www.cloudflare.com',
            'https://www.example.com'
        ]
        
        proxies = {
            'http': f'http://{proxy}',
            'https': f'http://{proxy}'
        }
        
        headers = {'User-Agent': self._get_random_user_agent()}
        
        for url in test_urls:
            try:
                response = requests.get(
                    url,
                    proxies=proxies,
                    headers=headers,
                    timeout=timeout,
                    verify=True
                )
                if response.status_code == 200:
                    return True
            except:
                continue
        return False

    def get_proxies(self, force_refresh: bool = False) -> List[str]:
        """Get a list of working proxies, using cache if available and not expired."""
        current_time = time.time()
        
        # Return cached proxies if they're still fresh
        if not force_refresh and self.cached_proxies and \
           (current_time - self.last_fetch_time) < self.min_fetch_interval:
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

            # Skip header row
            rows = table.find_all("tr")[1:]
            
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 7:  # Ensure we have all needed columns
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    https = cols[6].text.strip()
                    anonymity = cols[4].text.strip()
                    
                    # Only use HTTPS proxies with good anonymity
                    if https.lower() == 'yes' and anonymity.lower() in ['anonymous', 'elite proxy']:
                        proxy = f"{ip}:{port}"
                        proxies.append(proxy)

            # Test proxies in parallel
            working_proxies = []
            logging.info(f"Testing {len(proxies)} potential proxies...")
            
            for proxy in proxies:
                if self._test_proxy(proxy):
                    working_proxies.append(proxy)
                    logging.info(f"Found working proxy: {proxy}")
                
                # If we have enough working proxies, stop testing
                if len(working_proxies) >= 20:
                    break

            if working_proxies:
                self.cached_proxies = working_proxies
                self.last_fetch_time = current_time
                return working_proxies
            else:
                logging.warning("No working proxies found")
                return self.cached_proxies if self.cached_proxies else []

        except Exception as e:
            logging.error(f"Error fetching proxies: {str(e)}")
            return self.cached_proxies if self.cached_proxies else []


# Create a global instance
proxy_fetcher = ProxyFetcher()

def get_free_proxies() -> List[str]:
    """Get a list of working proxies."""
    return proxy_fetcher.get_proxies()
