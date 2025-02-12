import requests
import logging
import time
from typing import Dict, Optional, List
from urllib.parse import urlparse
import pycountry

class ProxyIdentity:
    def __init__(self, proxy: str):
        self.proxy = proxy
        self.country = self._get_proxy_country()
        self.session_start = time.time()
        self.request_count = 0
        self.last_sites = []  # Track visited sites for this identity
        self.success_rate = 1.0
        self.last_success = time.time()
        self.failure_count = 0
        self.max_failures = 3
        self.max_requests = 100
        self.domain_delays: Dict[str, float] = {}  # Track per-domain delays
        
    def _get_proxy_country(self) -> Optional[str]:
        """Determine the country of the proxy."""
        try:
            # Try multiple IP info services
            services = [
                'https://ipapi.co/{}/country',
                'https://ip-api.com/json/{}',
                'https://ipinfo.io/{}/country'
            ]
            
            ip = self.proxy.split(':')[0]
            
            for service in services:
                try:
                    url = service.format(ip)
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        country = response.text.strip()
                        if len(country) == 2:  # ISO country code
                            return country
                        # Try to convert country name to code
                        try:
                            country_obj = pycountry.countries.get(name=country)
                            if country_obj:
                                return country_obj.alpha_2
                        except:
                            continue
                except:
                    continue
                    
        except Exception as e:
            logging.warning(f"Could not determine proxy country: {str(e)}")
            
        return None

    def get_proxies(self) -> Dict[str, str]:
        """Get proxy configuration."""
        return {
            'http': f'http://{self.proxy}',
            'https': f'http://{self.proxy}'
        }

    def is_suitable_for_url(self, url: str) -> bool:
        """Determine if this proxy is suitable for the given URL."""
        domain = urlparse(url).netloc
        
        # Check if we've failed too many times
        if self.failure_count >= self.max_failures:
            return False
            
        # Check if we've made too many requests
        if self.request_count >= self.max_requests:
            return False
            
        # Check if we need to wait for this domain
        if domain in self.domain_delays:
            if time.time() < self.domain_delays[domain]:
                return False
                
        # Check geographic relevance
        if self.country:
            # Extract target country from URL or domain
            target_country = self._get_target_country(url, domain)
            if target_country and target_country != self.country:
                # Allow some exceptions for global domains
                if not self._is_global_domain(domain):
                    return False
        
        # Check if this proxy has recently accessed similar URLs
        if self._is_suspicious_pattern(url):
            return False
            
        return True

    def _get_target_country(self, url: str, domain: str) -> Optional[str]:
        """Try to determine target country from URL or domain."""
        # Check domain TLD
        tld = domain.split('.')[-1].upper()
        if len(tld) == 2 and tld not in ['IO', 'CO', 'AI']:
            return tld
            
        # Check URL path for country codes
        path = urlparse(url).path.lower()
        for country in pycountry.countries:
            if f"/{country.alpha_2.lower()}/" in path:
                return country.alpha_2
            
        return None

    def _is_global_domain(self, domain: str) -> bool:
        """Check if domain is a global service."""
        global_domains = [
            'lever.co',
            'greenhouse.io',
            'ashbyhq.com',
            'workday.com',
            'linkedin.com'
        ]
        return any(d in domain for d in global_domains)

    def _is_suspicious_pattern(self, url: str) -> bool:
        """Check if accessing this URL would create a suspicious pattern."""
        domain = urlparse(url).netloc
        
        # Check rapid repeated access to same domain
        domain_visits = sum(1 for site in self.last_sites[-5:] if domain in site)
        if domain_visits >= 3:
            return True
            
        # Check if we're jumping between too many different domains
        recent_domains = set(urlparse(site).netloc for site in self.last_sites[-3:])
        if len(recent_domains) >= 3 and domain not in recent_domains:
            return True
            
        return False

    def mark_request(self, url: str, success: bool, status_code: Optional[int] = None):
        """Update proxy status after a request."""
        self.request_count += 1
        domain = urlparse(url).netloc
        
        if success:
            self.last_success = time.time()
            self.last_sites.append(url)
            if len(self.last_sites) > 10:
                self.last_sites.pop(0)
            
            # Update success rate
            self.success_rate = ((self.success_rate * (self.request_count - 1)) + 1) / self.request_count
            
            # Clear domain delay if exists
            if domain in self.domain_delays:
                del self.domain_delays[domain]
                
        else:
            self.failure_count += 1
            self.success_rate = ((self.success_rate * (self.request_count - 1))) / self.request_count
            
            # Handle specific status codes
            if status_code == 429:  # Rate limit
                self.domain_delays[domain] = time.time() + 300  # 5 minute cooldown
            elif status_code == 403:  # Forbidden
                self.domain_delays[domain] = time.time() + 600  # 10 minute cooldown
            
    def should_retire(self) -> bool:
        """Determine if this proxy should be retired."""
        # Check absolute failure count
        if self.failure_count >= self.max_failures:
            return True
            
        # Check success rate
        if self.request_count > 10 and self.success_rate < 0.7:
            return True
            
        # Check request count
        if self.request_count >= self.max_requests:
            return True
            
        # Check age
        if time.time() - self.session_start > 3600:  # 1 hour
            return True
            
        return False 