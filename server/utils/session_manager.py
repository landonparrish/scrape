import requests
import random
import time
import logging
from typing import Dict, Optional, List
from urllib.parse import urlparse, urljoin
from .browser_profile import BrowserProfile
from .proxy_identity import ProxyIdentity
from .content_validator import ContentValidator

class BrowserSession:
    def __init__(self, proxy_identity: Optional[ProxyIdentity] = None):
        self.session = requests.Session()
        self.proxy_identity = proxy_identity
        self.browser_profile = BrowserProfile(
            country_code=proxy_identity.country if proxy_identity else None
        )
        self.content_validator = ContentValidator()
        self.last_request_time = 0
        self.last_page_type = None
        self.last_content_length = 0
        self.visited_urls = []
        self.page_depth = 0
        
    def _calculate_natural_delay(self) -> float:
        """Calculate a natural delay between requests."""
        base_delay = 0
        
        # Add delay based on last content length (reading time)
        if self.last_content_length:
            words_per_minute = random.randint(200, 400)  # Average reading speed
            word_count = self.last_content_length / 5  # Rough estimate
            reading_time = (word_count / words_per_minute) * 60
            base_delay += min(reading_time, 15)  # Cap at 15 seconds
        
        # Add delay based on page type
        if self.last_page_type == 'listing':
            base_delay += random.uniform(2, 5)  # Quick scan of listings
        elif self.last_page_type == 'detail':
            base_delay += random.uniform(5, 10)  # Reading job details
        
        # Add random variance
        variance = random.uniform(0.5, 1.5)
        
        return base_delay * variance

    def _simulate_page_interaction(self):
        """Simulate user interaction with the page."""
        # Simulate scrolling
        scroll_time = random.uniform(1, 3)
        time.sleep(scroll_time)
        
        # Simulate mouse movements
        if random.random() < 0.3:  # 30% chance
            mouse_time = random.uniform(0.5, 1.5)
            time.sleep(mouse_time)

    def _prepare_request(self, url: str, method: str = 'GET') -> Dict:
        """Prepare request configuration."""
        config = {
            'headers': self.browser_profile.get_headers(url),
            'verify': True,
            'allow_redirects': True
        }
        
        if self.proxy_identity:
            config['proxies'] = self.proxy_identity.get_proxies()
            
        # Add referrer if we have previous URLs
        if self.visited_urls:
            config['headers']['Referer'] = self.visited_urls[-1]
            
        return config

    def _handle_rate_limit(self, response) -> bool:
        """Handle rate limiting and other special responses."""
        if response.status_code == 429:
            cooldown = int(response.headers.get('Retry-After', 30))
            logging.info(f"Rate limited. Cooling down for {cooldown} seconds")
            time.sleep(cooldown)
            return True
        return False

    def make_request(self, url: str, page_type: str = 'detail') -> Optional[requests.Response]:
        """Make a request with natural timing and behavior."""
        # Calculate and apply natural delay
        if self.last_request_time:
            delay = self._calculate_natural_delay()
            time.sleep(delay)
        
        # Prepare request
        config = self._prepare_request(url)
        
        try:
            # Make request
            response = self.session.get(url, **config)
            self.last_request_time = time.time()
            self.last_page_type = page_type
            
            # Store content length for timing calculations
            self.last_content_length = len(response.content)
            
            # Validate response
            if not self.content_validator.validate_response(response, page_type):
                logging.warning(f"Invalid content received for {url}")
                return None
            
            # Handle rate limiting
            if self._handle_rate_limit(response):
                return self.make_request(url, page_type)  # Retry
            
            # Update history
            self.visited_urls.append(url)
            if len(self.visited_urls) > 10:
                self.visited_urls.pop(0)
            
            # Simulate page interaction
            self._simulate_page_interaction()
            
            return response
            
        except Exception as e:
            logging.error(f"Request failed for {url}: {str(e)}")
            return None

    def visit_company_page(self, company_url: str) -> bool:
        """Visit company page before accessing jobs."""
        response = self.make_request(company_url, page_type='company')
        return response is not None and response.status_code == 200

    def browse_job_listings(self, listings_url: str) -> List[str]:
        """Browse job listings page and extract job URLs."""
        response = self.make_request(listings_url, page_type='listing')
        if not response or response.status_code != 200:
            return []
            
        # Extract job URLs (implementation depends on the specific job board)
        # This is a placeholder - actual implementation would parse the HTML
        return []

    def view_job_details(self, job_url: str) -> Optional[Dict]:
        """View individual job details."""
        response = self.make_request(job_url, page_type='detail')
        if not response or response.status_code != 200:
            return None
            
        # Parse job details (implementation depends on the specific job board)
        # This is a placeholder - actual implementation would parse the HTML
        return None 