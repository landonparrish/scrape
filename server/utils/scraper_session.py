import logging
from typing import Dict, List, Optional
from .browser_profile import BrowserProfile
from .proxy_identity import ProxyIdentity
from .session_manager import BrowserSession
from .content_validator import ContentValidator
import random
import time

class ScraperSession:
    def __init__(self):
        self.proxy_pool = []
        self.active_sessions = {}
        self.content_validator = ContentValidator()
        self.max_concurrent_sessions = 3
        self.session_timeout = 1800  # 30 minutes
        
    def _get_suitable_proxy(self, url: str) -> Optional[ProxyIdentity]:
        """Get a suitable proxy for the URL."""
        # Clean up retired proxies
        self.proxy_pool = [p for p in self.proxy_pool if not p.should_retire()]
        
        # Try to find a suitable existing proxy
        suitable_proxies = [p for p in self.proxy_pool if p.is_suitable_for_url(url)]
        if suitable_proxies:
            return random.choice(suitable_proxies)
            
        # If we need more proxies, get them from the proxy fetcher
        if len(self.proxy_pool) < self.max_concurrent_sessions:
            from .proxy import get_free_proxies
            new_proxies = get_free_proxies(force_refresh=True)
            for proxy in new_proxies:
                proxy_identity = ProxyIdentity(proxy)
                if proxy_identity.is_suitable_for_url(url):
                    self.proxy_pool.append(proxy_identity)
                    return proxy_identity
                    
        return None

    def _get_or_create_session(self, domain: str) -> Optional[BrowserSession]:
        """Get existing session or create new one for domain."""
        current_time = time.time()
        
        # Clean up expired sessions
        self.active_sessions = {
            d: s for d, s in self.active_sessions.items()
            if current_time - s.last_request_time < self.session_timeout
        }
        
        # Return existing session if available
        if domain in self.active_sessions:
            return self.active_sessions[domain]
            
        # Create new session if we're under limit
        if len(self.active_sessions) < self.max_concurrent_sessions:
            proxy_identity = self._get_suitable_proxy(f"https://{domain}")
            session = BrowserSession(proxy_identity)
            self.active_sessions[domain] = session
            return session
            
        return None

    def scrape_job(self, job_url: str) -> Optional[Dict]:
        """Scrape a job listing with proper session management."""
        from urllib.parse import urlparse
        domain = urlparse(job_url).netloc
        
        # Get or create session
        session = self._get_or_create_session(domain)
        if not session:
            logging.error(f"Could not create session for {domain}")
            return None
            
        try:
            # Extract company URL from job URL
            company_url = self._extract_company_url(job_url)
            
            # Visit company page first
            if company_url and not session.visit_company_page(company_url):
                logging.warning(f"Failed to visit company page: {company_url}")
            
            # Add some delay to simulate reading
            time.sleep(random.uniform(2, 5))
            
            # Visit job listing
            job_details = session.view_job_details(job_url)
            if not job_details:
                logging.error(f"Failed to get job details from {job_url}")
                return None
                
            return job_details
            
        except Exception as e:
            logging.error(f"Error scraping job {job_url}: {str(e)}")
            return None

    def scrape_jobs_from_listing(self, listing_url: str) -> List[Dict]:
        """Scrape multiple jobs from a listing page."""
        from urllib.parse import urlparse
        domain = urlparse(listing_url).netloc
        
        # Get or create session
        session = self._get_or_create_session(domain)
        if not session:
            logging.error(f"Could not create session for {domain}")
            return []
            
        try:
            # Get job URLs from listing
            job_urls = session.browse_job_listings(listing_url)
            if not job_urls:
                logging.warning(f"No job URLs found in {listing_url}")
                return []
                
            # Scrape each job
            jobs = []
            for job_url in job_urls:
                # Add delay between jobs
                time.sleep(random.uniform(3, 7))
                
                job_details = self.scrape_job(job_url)
                if job_details:
                    jobs.append(job_details)
                    
            return jobs
            
        except Exception as e:
            logging.error(f"Error scraping listing {listing_url}: {str(e)}")
            return []

    def _extract_company_url(self, job_url: str) -> Optional[str]:
        """Extract company page URL from job URL."""
        from urllib.parse import urlparse, urljoin
        
        try:
            parsed = urlparse(job_url)
            
            if 'lever.co' in parsed.netloc:
                # Lever URLs: https://jobs.lever.co/company/job-id
                parts = parsed.path.split('/')
                if len(parts) > 2:
                    return f"https://jobs.lever.co/{parts[1]}"
                    
            elif 'greenhouse.io' in parsed.netloc:
                # Greenhouse URLs: https://boards.greenhouse.io/company/jobs/job-id
                parts = parsed.path.split('/')
                if len(parts) > 2:
                    return f"https://boards.greenhouse.io/{parts[1]}"
                    
            elif 'ashbyhq.com' in parsed.netloc:
                # Ashby URLs: https://jobs.ashbyhq.com/company/job-id
                parts = parsed.path.split('/')
                if len(parts) > 2:
                    return f"https://jobs.ashbyhq.com/{parts[1]}"
                    
        except Exception as e:
            logging.warning(f"Error extracting company URL from {job_url}: {str(e)}")
            
        return None

# Create global instance
scraper_session = ScraperSession() 