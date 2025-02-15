from bs4 import BeautifulSoup
import requests
from utils.proxy import get_free_proxies, get_request_config, mark_request_result
from utils.text_processor import TextProcessor
from enum import Enum
import yagooglesearch
import re
import logging
from datetime import datetime, timedelta
import hashlib
import time
from typing import Optional
import random
import os


class JobSite(Enum):
    LEVER = "lever.co"
    GREENHOUSE = "boards.greenhouse.io/*/jobs/*"
    ASHBY = "ashbyhq.com"
    WELLFOUND = "TODO"
    ANGELLIST = "TODO"
    WORKABLE = "TODO"
    INDEED = "TODO"
    GLASSDOOR = "TODO"
    LINKEDIN = "TODO"
    CUSTOM = "TODO"
    


class TBS(Enum):
    PAST_TWELVE_HOURS = "qdr:h12"
    PAST_DAY = "qdr:d"
    PAST_WEEK = "qdr:w"
    PAST_MONTH = "qdr:m"
    PAST_YEAR = "qdr:y"


def crawl_wellfound_jobs(location_url: str) -> list[str]:
    """Crawl Wellfound job listings from a location or category page."""
    job_urls = []
    page = 1
    
    while True:
        try:
            # Add page parameter if not first page
            url = location_url if page == 1 else "{}?page={}".format(location_url, page)
            logging.info("Crawling Wellfound page {}: {}".format(page, url))
            
            response = requests.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Find job links - try multiple selectors
            job_links = []
            # Method 1: Direct job links
            job_links.extend(soup.find_all("a", href=lambda x: x and "/jobs/" in x))
            # Method 2: Job cards
            job_links.extend(soup.find_all("a", class_=lambda x: x and "job-card" in str(x).lower()))
            # Method 3: Role links
            job_links.extend(soup.find_all("a", href=lambda x: x and "/role/" in x))
            
            if not job_links:
                logging.info("No job links found on page {}".format(page))
                break
                
            # Extract and normalize URLs
            for link in job_links:
                href = link.get("href")
                if href:
                    # Clean and normalize URL
                    if not href.startswith("http"):
                        if href.startswith("//"):
                            href = "https:" + href
                        else:
                            href = "https://wellfound.com" + href
                    
                    # Ensure it's a job URL
                    if "/jobs/" in href or "/role/" in href:
                        job_urls.append(href)
            
            # Check if there's a next page
            next_button = (
                soup.find("a", string=lambda x: x and "Next" in x) or
                soup.find("button", string=lambda x: x and "Next" in x) or
                soup.find("a", class_=lambda x: x and "next" in str(x).lower())
            )
            
            if not next_button or "disabled" in str(next_button.get("class", [])):
                logging.info("No more pages found after page {}".format(page))
                break
                
            page += 1
            if page > 20:  # Safety limit
                logging.info("Reached maximum page limit")
                break
            
        except Exception as e:
            logging.error("Error crawling Wellfound page {}: {}".format(page, str(e)))
            break
    
    # Clean and deduplicate URLs
    cleaned_urls = list(set(job_urls))
    logging.info("Found {} unique Wellfound job URLs".format(len(cleaned_urls)))
    return cleaned_urls


def find_jobs(
    keyword: str,
    job_sites: list[JobSite],
    tbs: TBS | None,
    max_results: int = 1000,
    location_urls: dict[JobSite, str] | None = None,
):
    """
    Find jobs using Google search or direct crawling.
    :param location_urls: Optional dict mapping JobSite to location/category URLs for direct crawling
    """
    job_urls_by_board = {}

    # First try direct crawling if location URLs are provided
    if location_urls:
        for job_site, url in location_urls.items():
            if job_site == JobSite.LEVER:
                job_urls_by_board[job_site] = crawl_lever_jobs(url)
            elif job_site == JobSite.GREENHOUSE:
                job_urls_by_board[job_site] = crawl_greenhouse_jobs(url)
            elif job_site == JobSite.ASHBY:
                job_urls_by_board[job_site] = crawl_ashby_jobs(url)

    # Then do Google search for remaining job sites
    remaining_sites = [site for site in job_sites if site not in job_urls_by_board]
    if remaining_sites:
        search_sites = " OR ".join([f"site:{site.value}" for site in remaining_sites])
        search_query = f"{keyword} {search_sites}"
        logging.info(f"Searching for {search_query}")
        
        # Split into multiple searches with different time ranges to get more results
        time_ranges = [TBS.PAST_TWELVE_HOURS, TBS.PAST_DAY, TBS.PAST_WEEK] if not tbs else [tbs]
        all_results = []
        
        max_retries = 3
        retry_delay = 5
        
        for time_range in time_ranges:
            for attempt in range(max_retries):
                try:
                    # Configure search client with proper settings
                    client_args = {
                        "query": search_query,
                        "tbs": time_range.value,
                        "max_search_result_urls_to_return": max_results // len(time_ranges),
                        "verbosity": 0,
                        "verify_ssl": False,  # Handle SSL verification in our request config
                    }
                    
                    client = yagooglesearch.SearchClient(**client_args)
                    client.assign_random_user_agent()
                    
                    # Get request configuration from our proxy manager
                    config = get_request_config("https://www.google.com")
                    
                    # Set proxy if provided in config
                    if config.get('proxies'):
                        os.environ['HTTP_PROXY'] = config['proxies']['http']
                        os.environ['HTTPS_PROXY'] = config['proxies']['https']
                    
                    # Perform search
                    results = client.search()
                    all_results.extend(results)
                    
                    # Clear proxy environment variables
                    if 'HTTP_PROXY' in os.environ:
                        del os.environ['HTTP_PROXY']
                    if 'HTTPS_PROXY' in os.environ:
                        del os.environ['HTTPS_PROXY']
                    
                    # Mark successful request
                    mark_request_result("https://www.google.com", success=True)
                    
                    # Add a random delay between searches
                    time.sleep(random.uniform(2, 5))
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    error_msg = str(e)
                    logging.error(f"Error searching with time range {time_range}: {error_msg}")
                    
                    # Mark failed request
                    mark_request_result("https://www.google.com", success=False)
                    
                    if attempt < max_retries - 1:
                        # Calculate exponential backoff delay
                        delay = retry_delay * (2 ** attempt) + random.uniform(0, 1)
                        logging.info(f"Retrying in {delay:.2f} seconds...")
                        time.sleep(delay)
                        continue
                    
                    # Clear proxy environment variables on failure
                    if 'HTTP_PROXY' in os.environ:
                        del os.environ['HTTP_PROXY']
                    if 'HTTPS_PROXY' in os.environ:
                        del os.environ['HTTPS_PROXY']
            
        # Process results for each job site
        result = list(set(all_results))  # Remove duplicates
        for job_site in remaining_sites:
            job_urls_for_job_site = [
                url for url in result if re.search(regex[job_site], url)
            ]
            cleaner = JobSearchResultCleaner(job_site)
            job_urls_by_board[job_site] = cleaner.clean(job_urls_for_job_site)

    return job_urls_by_board


class ProxyRotator:
    def __init__(self):
        self.proxies = [None]  # Start with direct connection
        self.current_proxy_index = 0
        self.requests_with_current_proxy = 0
        self.max_requests_per_proxy = 15  # Reduced from 25 to be more conservative
        self.proxy_failures = {}  # Track failures per proxy
        self.max_failures = 2  # Reduced from 3 to be more aggressive about removing bad proxies
        self.last_rotation_time = time.time()
        self.min_rotation_interval = 30  # Reduced from 60 to rotate more frequently
        self.initialize()  # Initialize proxies immediately
        
    def initialize(self):
        """Initialize or refresh proxy list."""
        try:
            new_proxies = get_free_proxies()
            if new_proxies:
                # Test each proxy before adding it to the pool
                working_proxies = []
                for proxy in new_proxies:
                    if self._test_proxy(proxy):
                        working_proxies.append(proxy)
                        
                if working_proxies:
                    self.proxies = [None] + working_proxies  # Always keep direct connection as an option
                    self.proxy_failures = {proxy: 0 for proxy in self.proxies}
                    logging.info(f"Initialized proxy pool with {len(working_proxies)} working proxies")
                else:
                    logging.warning("No working proxies found, using direct connection")
                    self.proxies = [None]
                    self.proxy_failures = {None: 0}
        except Exception as e:
            logging.error(f"Error initializing proxies: {str(e)}")
            self.proxies = [None]
            self.proxy_failures = {None: 0}
    
    def _test_proxy(self, proxy, test_url="https://www.google.com"):
        """Test if a proxy is working."""
        try:
            proxies = {
                'http': proxy,
                'https': proxy
            }
            response = requests.get(
                test_url,
                proxies=proxies,
                timeout=5,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            return response.status_code == 200
        except:
            return False
    
    def get_current_proxy(self):
        """Get current proxy configuration."""
        if not self.proxies or len(self.proxies) <= self.current_proxy_index:
            self.initialize()
            self.current_proxy_index = 0
            
        current_proxy = self.proxies[self.current_proxy_index]
        if current_proxy:
            return {
                'http': current_proxy,
                'https': current_proxy
            }
        return None
    
    def should_rotate(self, status_code=None):
        """Determine if we should rotate to next proxy."""
        # Always rotate on rate limit, forbidden, or proxy errors
        if status_code in [429, 403, 407, 502, 503, 504]:
            return True
            
        # Rotate if we've used this proxy too much
        if self.requests_with_current_proxy >= self.max_requests_per_proxy:
            return True
            
        # Rotate if minimum time has passed
        if time.time() - self.last_rotation_time >= self.min_rotation_interval:
            return True
            
        return False
    
    def mark_success(self):
        """Mark current proxy as successful."""
        self.requests_with_current_proxy += 1
    
    def mark_failure(self, error=None):
        """Mark current proxy as failed."""
        current_proxy = self.proxies[self.current_proxy_index]
        self.proxy_failures[current_proxy] = self.proxy_failures.get(current_proxy, 0) + 1
        
        # Force rotation on connection errors or if proxy is failing too much
        if isinstance(error, requests.exceptions.RequestException):
            error_str = str(error).lower()
            if any(term in error_str for term in [
                'timeout', 'blocked', 'forbidden', 'rate', 
                'connection refused', 'connection error', 'proxy error'
            ]):
                self.rotate_proxy()
                
        # If this proxy has failed too many times, force rotation
        if self.proxy_failures[current_proxy] >= self.max_failures:
            self.rotate_proxy()
    
    def rotate_proxy(self):
        """Rotate to next available proxy."""
        # Remove proxies that have failed too many times
        self.proxies = [p for p in self.proxies if self.proxy_failures.get(p, 0) < self.max_failures]
        
        # If we're running low on proxies, get new ones
        if len(self.proxies) < 3:
            self.initialize()
        
        # If we still have no proxies, use direct connection
        if not self.proxies:
            self.proxies = [None]
            self.current_proxy_index = 0
        else:
            # Move to next proxy
            self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
            
        self.requests_with_current_proxy = 0
        self.last_rotation_time = time.time()
        
        current_proxy = self.proxies[self.current_proxy_index]
        logging.info(f"Rotating to {'direct connection' if current_proxy is None else f'proxy {current_proxy}'}")

# Initialize global proxy rotator
proxy_rotator = ProxyRotator()

def make_request(url: str, max_retries: int = 3) -> Optional[requests.Response]:
    """Make an HTTP request with proxy rotation and retry logic."""
    for attempt in range(max_retries):
        try:
            # Get request configuration (includes headers and proxy if needed)
            config = get_request_config(url)
            
            # Add exponential backoff between retries
            if attempt > 0:
                sleep_time = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(sleep_time)
            
            response = requests.get(url, **config, timeout=10)
            
            if response.status_code == 200:
                mark_request_result(url, success=True)
                
                # Add a small delay between requests
                time.sleep(random.uniform(1, 3))
                
                return response
            else:
                mark_request_result(url, success=False, status_code=response.status_code)
                
                # If we got rate limited or forbidden, retry with different config
                if response.status_code in [429, 403]:
                    continue
                
                response.raise_for_status()
            
        except Exception as e:
            mark_request_result(url, success=False)
            logging.warning(f"Request failed for {url} (attempt {attempt + 1}/{max_retries}): {str(e)}")
            
            if attempt == max_retries - 1:
                logging.error(f"Failed to fetch {url} after {max_retries} attempts")
                return None
    
    return None

def get_job_page_with_retry(url: str, max_retries: int = 3) -> Optional[BeautifulSoup]:
    """Fetch and parse a job page with retry logic and proxy rotation."""
    response = make_request(url, max_retries)
    if not response:
        return None
        
    try:
        # Try multiple encodings if default fails
        content = None
        encodings = ['utf-8', 'iso-8859-1', 'cp1252', 'latin1']
        
        for encoding in encodings:
            try:
                content = response.content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if not content:
            content = response.text  # Fallback to requests' auto-detection
        
        # Parse with more lenient settings
        soup = BeautifulSoup(content, "html.parser", from_encoding='utf-8')
        
        # Verify we got actual content
        if not soup or not soup.find("body"):
            raise ValueError("Invalid or empty HTML content")
        
        return soup
        
    except Exception as e:
        logging.error(f"Error parsing content from {url}: {str(e)}")
        return None

def crawl_lever_jobs(base_url: str) -> list[str]:
    """Crawl Lever job board directly."""
    job_urls = []
    try:
        response = make_request(base_url)
        if not response:
            return []
            
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Find all job links
        for link in soup.find_all("a", href=re.compile(r"https://jobs\.lever\.co/[^/]+/[^/]+")):
            job_urls.append(link["href"])
            
    except Exception as e:
        logging.error(f"Error crawling Lever jobs from {base_url}: {str(e)}")
    
    return list(set(job_urls))

def crawl_greenhouse_jobs(base_url: str) -> list[str]:
    """Crawl Greenhouse job board directly."""
    job_urls = []
    try:
        response = make_request(base_url)
        if not response:
            return []
            
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Find all job links
        for link in soup.find_all("a", href=re.compile(r"/jobs/\d+")):
            href = link["href"]
            if not href.startswith("http"):
                href = f"https://boards.greenhouse.io{href}"
            job_urls.append(href)
            
    except Exception as e:
        logging.error(f"Error crawling Greenhouse jobs from {base_url}: {str(e)}")
    
    return list(set(job_urls))

def crawl_ashby_jobs(base_url: str) -> list[str]:
    """Crawl Ashby job board directly."""
    job_urls = []
    try:
        response = make_request(base_url)
        if not response:
            return []
            
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Find all job links
        for link in soup.find_all("a", href=re.compile(r"https://jobs\.ashbyhq\.com/[^/]+/[a-f0-9-]+")):
            job_urls.append(link["href"])
            
    except Exception as e:
        logging.error(f"Error crawling Ashby jobs from {base_url}: {str(e)}")
    
    return list(set(job_urls))

def get_lever_job_details(link: str) -> dict:
    try:
        response = make_request(link)
        if not response:
            return None
            
        soup = BeautifulSoup(response.content, "html.parser")

        # Basic job info
        title = soup.title.string if soup.title else "Unknown"
        company_name = title.split("-")[0].strip() if "-" in title else title.strip()
        position = "-".join(title.split("-")[1:]).strip() if "-" in title else "Unknown"

        # Company Logo
        img = soup.find("img")
        company_logo = None
        if img and img.get("src") and img["src"] != "/img/lever-logo-full.svg":
            company_logo = img["src"]

        # Location
        location_elem = soup.find("div", {"class": "location"}) or soup.find("div", {"class": "workplaceTypes"})
        location = location_elem.text.strip() if location_elem else ""

        # Enhanced section detection
        requirements = []
        qualifications = []
        benefits = []
        description_parts = []

        # First try to get main content
        main_content = soup.find("div", {"class": "content"}) or soup.find("div", {"class": "description"})
        if main_content:
            main_description = main_content.decode_contents()
            description_parts.append(TextProcessor.clean_html(main_description))

        # Process each section
        for section in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5']):
            section_title = section.get_text().strip()
            section_type = TextProcessor.identify_section(section_title)
            
            # Get the content following this section header
            content = []
            current = section.find_next()
            while current and current.name not in ['h1', 'h2', 'h3', 'h4', 'h5']:
                if current.name in ['p', 'li', 'ul', 'div']:
                    content.append(current.decode_contents())
                current = current.find_next()
            
            # Clean the content
            cleaned_content = TextProcessor.clean_html('\n'.join(content))
            
            # Sort into appropriate category
            if section_type == 'requirements':
                requirements.extend(TextProcessor.extract_bullet_points(cleaned_content))
            elif section_type == 'benefits':
                benefits.extend(TextProcessor.extract_bullet_points(cleaned_content))
            else:
                description_parts.append(cleaned_content)

        # Combine description parts
        description = '\n\n'.join(description_parts) if description_parts else "No description available"

        # Employment Type
        employment_type = "full-time"  # Default
        employment_elem = soup.find("div", {"class": "commitment"})
        if employment_elem:
            employment_type = employment_elem.text.strip().lower()

        # Remote Status and Work Types
        remote = False
        work_types = []
        workplace_elem = soup.find("div", {"class": "workplaceTypes"})
        if workplace_elem:
            workplace_text = workplace_elem.text.lower()
            if "remote" in workplace_text:
                remote = True
                work_types.append("remote")
            if "hybrid" in workplace_text:
                work_types.append("hybrid")
            if "on-site" in workplace_text or "onsite" in workplace_text or "in office" in workplace_text:
                work_types.append("on-site")
        
        # Also check location and description for work type indicators
        if location:
            if "remote" in location.lower():
                remote = True
                if "remote" not in work_types:
                    work_types.append("remote")
            if "hybrid" in location.lower() and "hybrid" not in work_types:
                work_types.append("hybrid")
            if any(x in location.lower() for x in ["on-site", "onsite", "in office"]) and "on-site" not in work_types:
                work_types.append("on-site")

        # Create job details
        job_details = {
            "title": position,
            "company": company_name,
            "location": location,
            "description": description,
            "salary": None,  # Lever rarely shows salary
            "remote": remote,
            "work_types": work_types,
            "employment_type": employment_type,
            "experience_level": None,  # Will be determined by text processor
            "requirements": requirements,
            "qualifications": qualifications,
            "benefits": benefits,
            "application_url": link,
            "company_logo": company_logo,
            "source": "lever",
            "posted_date": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_type": None,
            "scraped_at": datetime.now().isoformat(),
            "status": "active"
        }

        return TextProcessor.process_job_details(job_details)
    except Exception as e:
        logging.error("Error parsing Lever job details from {}: {}".format(link, str(e)))
        return None


def get_greenhouse_job_details(link: str) -> dict:
    """Get job details from a Greenhouse job posting with improved error handling."""
    try:
        soup = get_job_page_with_retry(link)
        if not soup:
            logging.warning(f"Failed to fetch Greenhouse job page: {link}")
            return None
            
        head = soup.find("head")
        if not head:
            logging.warning(f"No head section found in Greenhouse job page: {link}")
            return None

        # Basic job info with improved parsing
        title_elem = soup.find("h1")
        position = title_elem.text.strip() if title_elem else "Unknown"
    except Exception as e:
        logging.error(f"Error processing Greenhouse job page {link}: {str(e)}")
        return None

    # Company info with better error handling
    company_logo = None
    company_name = None
    
    try:
        # Try multiple ways to get company logo
        logo_elem = soup.find("img", {"class": "logo"}) or soup.find("img", {"alt": lambda x: x and "Logo" in x})
        if logo_elem and logo_elem.get("src"):
            company_logo = logo_elem["src"]
            if not company_logo.startswith("http"):
                company_logo = "https:" + company_logo if company_logo.startswith("//") else "https://" + company_logo
    except Exception as e:
        logging.warning(f"Error extracting company logo: {str(e)}")

    # Try to get company name from URL first, then fallback to other methods
    try:
        company_match = re.search(r'boards\.greenhouse\.io/([^/]+)', link)
        if company_match:
            company_name = company_match.group(1).replace("-", " ").title()
            # Clean up common suffixes
            company_name = re.sub(r'(?i)(usa|inc|llc|corp)$', '', company_name).strip()
    except Exception as e:
        logging.warning(f"Error extracting company name: {str(e)}")
        company_name = "Unknown Company"

    # Location with multiple location support
    locations = []
    location_elem = soup.find("div", {"class": "location"})
    if location_elem:
        # Split on common location separators and clean
        raw_locations = re.split(r'[;,]|\s*or\s*|\s*\|\s*', location_elem.text.strip())
        locations = [loc.strip() for loc in raw_locations if loc.strip()]
    location = "; ".join(locations) if locations else ""

    # Enhanced section detection
    requirements = []
    qualifications = []
    benefits = []
    description_parts = []

    # Look for specific section headers
    section_mapping = {
        r'(?i)about (the role|this position|this opportunity)': 'description',
        r'(?i)requirements|qualifications|what you.ll need|what we.re looking for': 'requirements',
        r'(?i)benefits|perks|what we offer|why join us': 'benefits',
        r'(?i)responsibilities|what you.ll do|key responsibilities': 'description',
        r'(?i)about (us|the team|the company)': 'description'
    }

    # Process each section
    for section in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5']):
        section_title = section.get_text().strip()
        section_type = 'other'
        
        # Determine section type based on patterns
        for pattern, s_type in section_mapping.items():
            if re.search(pattern, section_title, re.IGNORECASE):
                section_type = s_type
                break

        # Get the content following this section header
        content = []
        current = section.find_next()
        while current and current.name not in ['h1', 'h2', 'h3', 'h4', 'h5']:
            if current.name in ['p', 'li', 'ul', 'div']:
                content.append(current.decode_contents())
            current = current.find_next()

        # Clean and process the content
        cleaned_content = TextProcessor.clean_html('\n'.join(content))

        # Sort into appropriate category
        if section_type == 'requirements':
            requirements.extend(TextProcessor.extract_bullet_points(cleaned_content))
        elif section_type == 'benefits':
            benefits.extend(TextProcessor.extract_bullet_points(cleaned_content))
        else:
            description_parts.append(cleaned_content)

    # Combine description parts
    description = '\n\n'.join(description_parts)

    # Enhanced salary detection
    salary = None
    salary_min = None
    salary_max = None
    salary_currency = None
    salary_type = None

    # Look for salary in specific compensation sections and description
    salary_section = soup.find(lambda tag: tag.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'div'] and 
                             re.search(r'(?i)compensation|salary', tag.text))
    
    salary_patterns = [
        r'\$\d{2,3}(?:,\d{3})*(?:\s*-\s*\$\d{2,3}(?:,\d{3})*)?(?:\s*k)?(?:\s*per\s*year)?',
        r'\$\d{2,3}(?:,\d{3})*(?:\s*k)?(?:\s*-\s*\$\d{2,3}(?:,\d{3})*(?:\s*k)?)?',
        r'(?i)(\$\d{2,3}(?:,\d{3})*(?:\s*k)?)\s*(?:to|-)\s*(\$\d{2,3}(?:,\d{3})*(?:\s*k)?)',
        r'(?i)salary range[:\s]+(\$[\d,]+k?)\s*(?:to|-)\s*(\$[\d,]+k?)'
    ]

    salary_texts = [description]
    if salary_section:
        next_elem = salary_section.find_next()
        while next_elem and next_elem.name not in ['h1', 'h2', 'h3', 'h4', 'h5']:
            salary_texts.append(next_elem.get_text())
            next_elem = next_elem.find_next()

    for text in salary_texts:
        if not text:
            continue
        for pattern in salary_patterns:
            match = re.search(pattern, text)
            if match:
                salary = match.group(0)
                # Extract numbers
                numbers = re.findall(r'\d+(?:,\d{3})*(?:k)?', salary)
                if numbers:
                    # Convert k notation to full numbers
                    def parse_number(num):
                        num = num.replace(',', '')
                        if num.lower().endswith('k'):
                            return int(float(num[:-1]) * 1000)
                        return int(num)
                    
                    salary_min = parse_number(numbers[0])
                    if len(numbers) > 1:
                        salary_max = parse_number(numbers[1])
                    salary_currency = '$'
                    
                    # Determine salary type
                    if re.search(r'(?i)per\s*year|annual|yearly', text):
                        salary_type = 'yearly'
                    elif re.search(r'(?i)per\s*hour|hourly', text):
                        salary_type = 'hourly'
                    break
        if salary:
            break

    # Employment Type
    employment_type = "full-time"  # Default
    employment_patterns = {
        'full-time': r'(?i)full[- ]time|ft\b',
        'part-time': r'(?i)part[- ]time|pt\b',
        'contract': r'(?i)contract|contractor',
        'temporary': r'(?i)temporary|temp\b',
        'internship': r'(?i)internship|intern\b'
    }
    
    for etype, pattern in employment_patterns.items():
        if re.search(pattern, description) or (title_elem and re.search(pattern, title_elem.text)):
            employment_type = etype
            break

    # Remote Status and Work Types
    remote = False
    work_types = []
    
    # Check location and description for work type indicators
    texts_to_check = [location, description]
    for text in texts_to_check:
        if text:
            text_lower = text.lower()
            if any(term in text_lower for term in ['remote', 'work from home', 'wfh']):
                remote = True
                if "remote" not in work_types:
                    work_types.append("remote")
            if "hybrid" in text_lower and "hybrid" not in work_types:
                work_types.append("hybrid")
            if any(x in text_lower for x in ["on-site", "onsite", "in office", "in-office"]) and "on-site" not in work_types:
                work_types.append("on-site")

    # Experience Level
    experience_level = None
    experience_patterns = [
        (r'\b(?:senior|sr\.?\s*|lead)\b', 'senior'),
        (r'\b(?:junior|jr\.?\s*)\b', 'junior'),
        (r'\b(?:mid[- ]level|mid\s+senior)\b', 'mid-level'),
        (r'\b(?:principal|staff|director)\b', 'principal'),
        (r'\b(?:entry[- ]level|fresh\s*graduate|new\s*grad|associate)\b', 'entry-level')
    ]
    
    for pattern, level in experience_patterns:
        if re.search(pattern, position.lower()) or re.search(pattern, description.lower()):
            experience_level = level
            break

    # Posted Date and Expiration
    posted_date = datetime.now().isoformat()  # Default to now if not found
    expires_at = (datetime.now() + timedelta(days=30)).isoformat()  # Default to 30 days from now

    # Try to find actual posted date
    for meta in head.find_all("meta"):
        if meta.get("property") == "article:published_time":
            posted_date = meta.get("content")
            break

    # Create job details with safe defaults
    job_details = {
        "title": position or "Unknown Position",
        "company": company_name or "Unknown Company",
        "location": location or "",
        "description": description or "",
        "salary": salary,
        "remote": remote,
        "work_types": work_types or [],
        "employment_type": employment_type or "full-time",
        "experience_level": experience_level,
        "requirements": requirements or [],
        "qualifications": qualifications or [],
        "benefits": benefits or [],
        "application_url": link,
        "company_logo": company_logo,
        "source": "greenhouse",
        "posted_date": posted_date,
        "expires_at": expires_at,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": salary_currency,
        "salary_type": salary_type,
        "scraped_at": datetime.now().isoformat(),
        "status": "active"
    }

    return TextProcessor.process_job_details(job_details)


def get_ashby_job_details(link: str) -> dict:
    """Get job details from an Ashby job posting."""
    try:
        response = requests.get(link)
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Enhanced title extraction with multiple fallback methods
        position = None
        
        # Method 1: Look for data-testid="job-title"
        title_elem = soup.find("h1", {"data-testid": "job-title"})
        if title_elem:
            position = title_elem.text.strip()
            logging.info(f"Found title using data-testid: {position}")
        
        # Method 2: Look for og:title meta tag
        if not position:
            meta_title = soup.find("meta", property="og:title")
            if meta_title:
                title_content = meta_title["content"]
                # Usually in format "Job Title at Company Name"
                if " at " in title_content:
                    position = title_content.split(" at ")[0].strip()
                else:
                    position = title_content.strip()
                logging.info(f"Found title using og:title: {position}")
        
        # Method 3: Look for any h1 that might contain the job title
        if not position:
            h1_tags = soup.find_all("h1")
            for h1 in h1_tags:
                text = h1.text.strip()
                if text and not any(x in text.lower() for x in ["welcome", "about us", "join us"]):
                    position = text
                    logging.info(f"Found title using h1: {position}")
                    break
        
        # Method 4: Extract from URL as last resort
        if not position:
            job_id_match = re.search(r'/([a-f0-9-]+)(?:/application)?$', link)
            if job_id_match:
                # Convert job ID to title case as a last resort
                position = job_id_match.group(1).replace('-', ' ').title()
                logging.info(f"Generated title from URL: {position}")

        # If we still don't have a title, use a placeholder
        if not position:
            position = "Open Position"
            logging.warning(f"No title found for {link}, using placeholder")
        
        # Company info - try multiple methods
        company_name = None
        # Method 1: From URL
        company_match = re.search(r'jobs\.ashbyhq\.com/([^/]+)', link)
        if company_match:
            company_name = company_match.group(1).replace("-", " ").title()
        
        # Method 2: From meta tags
        if not company_name:
            meta_title = soup.find("meta", property="og:title")
            if meta_title:
                title_parts = meta_title["content"].split(" at ")
                if len(title_parts) > 1:
                    company_name = title_parts[1].strip()

        # Company Logo - Ashby uses og:image for company logos
        company_logo = None
        meta_image = soup.find("meta", property="og:image")
        if meta_image:
            company_logo = meta_image["content"]

        # Location - Ashby has specific data-testid for location
        location = ""
        location_elem = soup.find("div", {"data-testid": "job-location"})
        if location_elem:
            location = location_elem.text.strip()

        # Job description and sections
        description_parts = []
        requirements = []
        benefits = []
        
        # Main content is in data-testid="job-description"
        main_content = soup.find("div", {"data-testid": "job-description"})
        if main_content:
            current_section = "description"
            current_content = []
            
            for elem in main_content.children:
                if elem.name in ['h1', 'h2', 'h3', 'h4', 'h5']:
                    # Process previous section
                    if current_content:
                        cleaned = TextProcessor.clean_html('\n'.join(map(str, current_content)))
                        if current_section == 'requirements':
                            requirements.extend(TextProcessor.extract_bullet_points(cleaned))
                        elif current_section == 'benefits':
                            benefits.extend(TextProcessor.extract_bullet_points(cleaned))
                        else:
                            description_parts.append(cleaned)
                    
                    # Determine new section
                    heading = elem.get_text().lower().strip()
                    if any(kw in heading for kw in ["requirement", "qualification", "what you'll need", "what we're looking for"]):
                        current_section = "requirements"
                    elif any(kw in heading for kw in ["benefit", "perks", "what we offer", "why join us", "what's in it for you"]):
                        current_section = "benefits"
                    else:
                        current_section = "description"
                    current_content = []
                else:
                    text = elem.get_text().strip()
                    if text:
                        current_content.append(text)
            
            # Process the last section
            if current_content:
                cleaned = TextProcessor.clean_html('\n'.join(map(str, current_content)))
                if current_section == 'requirements':
                    requirements.extend(TextProcessor.extract_bullet_points(cleaned))
                elif current_section == 'benefits':
                    benefits.extend(TextProcessor.extract_bullet_points(cleaned))
                else:
                    description_parts.append(cleaned)

        # Combine description parts
        description = '\n\n'.join(description_parts)

        # Work types and remote status
        remote = False
        work_types = []
        
        # Check location and description for work type indicators
        texts_to_check = [location, description]
        for text in texts_to_check:
            if text:
                text_lower = text.lower()
                if any(term in text_lower for term in ['remote', 'work from home', 'wfh']):
                    remote = True
                    if "remote" not in work_types:
                        work_types.append("remote")
                if "hybrid" in text_lower and "hybrid" not in work_types:
                    work_types.append("hybrid")
                if any(x in text_lower for x in ["on-site", "onsite", "in office", "in-office"]) and "on-site" not in work_types:
                    work_types.append("on-site")

        # Create job details with all required fields
        job_details = {
            "title": position,
            "company": company_name,
            "location": location,
            "description": description,
            "requirements": requirements,
            "qualifications": [],  # Empty list as Ashby doesn't separate qualifications
            "benefits": benefits,
            "company_logo": company_logo,
            "remote": remote,
            "work_types": work_types,
            "employment_type": "full-time",  # Default
            "experience_level": None,  # Will be determined by text processor
            "salary": None,  # Ashby rarely shows salary
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_type": None,
            "application_url": link,
            "source": "ashby",
            "posted_date": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "scraped_at": datetime.now().isoformat(),
            "status": "active"
        }
            
        return TextProcessor.process_job_details(job_details)
            
    except Exception as e:
        logging.error(f"Error parsing Ashby job details from {link}: {str(e)}")
        return None


def get_wellfound_job_details(link: str) -> dict:
    """Get job details from a Wellfound job posting with improved error handling."""
    try:
        soup = get_job_page_with_retry(link)
        if not soup:
            logging.warning(f"Failed to fetch Wellfound job page: {link}")
            return None

        # Initialize job details with safe defaults
        job_details = {
            "title": "Unknown Position",
            "company": "Unknown Company",
            "company_logo": None,
            "location": "",
            "description": "",
            "requirements": [],
            "benefits": [],
            "salary": None,
            "employment_type": "full-time",
            "work_types": [],
            "remote": False,
            "experience_level": None,
            "posted_date": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "application_url": link,
            "source": "wellfound",
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_type": None
        }
        
        try:
            # Extract job title
            title_elem = soup.find("h1") or soup.find("h2", class_=lambda x: x and "title" in x.lower())
            if title_elem:
                job_details["title"] = title_elem.get_text().strip()
                
            # Extract company info
            company_elem = soup.find("a", href=lambda x: x and "/company/" in x) or \
                          soup.find("div", class_=lambda x: x and "company" in x.lower())
            if company_elem:
                job_details["company"] = company_elem.get_text().strip()
                
            # Extract company logo
            logo_elem = soup.find("img", class_=lambda x: x and ("logo" in x.lower() or "company" in x.lower()))
            if logo_elem and logo_elem.get("src"):
                job_details["company_logo"] = logo_elem["src"]
                
            # Extract location and work type information
            location_elem = soup.find("div", class_=lambda x: x and "location" in x.lower()) or \
                           soup.find("span", class_=lambda x: x and "location" in x.lower())
            if location_elem:
                location = location_elem.get_text().strip()
                job_details["location"] = location
                
                # Check for remote/hybrid indicators
                location_lower = location.lower()
                if any(term in location_lower for term in ['remote', 'work from home', 'wfh']):
                    job_details["remote"] = True
                    if "remote" not in job_details["work_types"]:
                        job_details["work_types"].append("remote")
                if "hybrid" in location_lower and "hybrid" not in job_details["work_types"]:
                    job_details["work_types"].append("hybrid")
                if any(x in location_lower for x in ["on-site", "onsite", "in office", "in-office"]) and "on-site" not in job_details["work_types"]:
                    job_details["work_types"].append("on-site")

            # Extract salary information
            salary_elem = soup.find(string=lambda x: x and any(s in x.lower() for s in ["salary", "compensation"]))
            if salary_elem:
                parent = salary_elem.parent
                salary_text = parent.get_text() if parent else salary_elem
                # Extract salary range using regex
                salary_match = re.search(r'\$[\d,]+(?:\s*-\s*\$[\d,]+)?(?:\s*(?:k|K|thousand|million|M))?\s*(?:per\s*(?:year|month|week|hr|hour|annum|yr))?', salary_text)
                if salary_match:
                    job_details["salary"] = salary_match.group(0)
                    
                    # Try to extract salary min/max
                    numbers = re.findall(r'\d+(?:,\d{3})*(?:k)?', job_details["salary"])
                    if numbers:
                        def parse_number(num):
                            num = num.replace(',', '')
                            if num.lower().endswith('k'):
                                return int(float(num[:-1]) * 1000)
                            return int(num)
                        
                        job_details["salary_min"] = parse_number(numbers[0])
                        if len(numbers) > 1:
                            job_details["salary_max"] = parse_number(numbers[1])
                        job_details["salary_currency"] = "$"
                        
                        if re.search(r'(?i)per\s*year|annual|yearly', salary_text):
                            job_details["salary_type"] = "yearly"
                        elif re.search(r'(?i)per\s*hour|hourly', salary_text):
                            job_details["salary_type"] = "hourly"

            # Extract employment type
            type_elem = soup.find(string=lambda x: x and "employment type" in x.lower())
            if type_elem:
                parent = type_elem.parent
                if parent:
                    type_text = parent.get_text().lower()
                    if "full" in type_text:
                        job_details["employment_type"] = "full-time"
                    elif "part" in type_text:
                        job_details["employment_type"] = "part-time"
                    elif "contract" in type_text:
                        job_details["employment_type"] = "contract"
                    elif "intern" in type_text:
                        job_details["employment_type"] = "internship"

            # Extract experience level
            exp_patterns = [
                (r'\b(?:senior|sr\.?\s*|lead)\b', 'senior'),
                (r'\b(?:junior|jr\.?\s*)\b', 'junior'),
                (r'\b(?:mid[- ]level|mid\s+senior)\b', 'mid-level'),
                (r'\b(?:principal|staff|director)\b', 'principal'),
                (r'\b(?:entry[- ]level|fresh\s*graduate|new\s*grad)\b', 'entry-level')
            ]
            
            for pattern, level in exp_patterns:
                if re.search(pattern, job_details["title"].lower()) or \
                   (job_details.get("description") and re.search(pattern, job_details["description"].lower())):
                    job_details["experience_level"] = level
                    break

            # Extract sections (description, requirements, benefits)
            main_content = soup.find("div", class_=lambda x: x and any(c in x.lower() for c in ["description", "content", "details"]))
            if main_content:
                sections = {}
                current_section = "description"
                current_text = []
                
                for elem in main_content.children:
                    if elem.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                        # Save previous section
                        if current_text:
                            sections[current_section] = "\n".join(current_text)
                            current_text = []
                        
                        # Determine new section
                        heading = elem.get_text().lower().strip()
                        if any(kw in heading for kw in ["requirement", "qualification", "what you'll need"]):
                            current_section = "requirements"
                        elif any(kw in heading for kw in ["benefit", "perks", "what we offer"]):
                            current_section = "benefits"
                        elif "about" in heading:
                            current_section = "description"
                        else:
                            current_section = "description"
                    else:
                        text = elem.get_text().strip()
                        if text:
                            current_text.append(text)
                
                # Save last section
                if current_text:
                    sections[current_section] = "\n".join(current_text)
                
                # Process sections
                for section, content in sections.items():
                    if section == "description":
                        job_details["description"] = content
                    elif section == "requirements":
                        job_details["requirements"] = TextProcessor.extract_bullet_points(content)
                    elif section == "benefits":
                        job_details["benefits"] = TextProcessor.extract_bullet_points(content)

            # If no sections were found, try to get all content
            if not job_details["description"] and main_content:
                description_elems = main_content.find_all(["p", "ul", "ol"])
                job_details["description"] = "\n".join(elem.get_text().strip() for elem in description_elems if elem.get_text().strip())
                
        except Exception as e:
            logging.warning(f"Error extracting specific field from Wellfound job {link}: {str(e)}")
            
        return TextProcessor.process_job_details(job_details)
        
    except Exception as e:
        logging.error(f"Error parsing Wellfound job {link}: {str(e)}", exc_info=True)
        return None


def normalize_job_url(url: str) -> str:
    """Normalize job URLs to a standard format for deduplication."""
    # Remove query parameters and fragments
    url = re.sub(r'[?#].*$', '', url)
    # Remove trailing slashes
    url = url.rstrip('/')
    # Remove /apply suffix
    url = re.sub(r'/apply$', '', url)
    # Convert to lowercase
    url = url.lower()
    return url


def generate_job_hash(job_details: dict) -> str:
    """Generate a unique hash for a job based on key fields."""
    # Create a string combining key fields that should make a job unique
    unique_string = "{}:{}:{}:{}".format(
        job_details['company'],
        job_details['title'],
        job_details['location'],
        normalize_job_url(job_details['application_url'])
    )
    # Create a hash of the string
    return hashlib.md5(unique_string.encode()).hexdigest()


def handle_job_insert(supabase: any, job_urls: list[tuple[str, str]], job_site: JobSite):
    """Handle job insertion with deduplication and improved error handling."""
    processed_urls = set()  # Track processed URLs
    processed_count = 0
    error_count = 0
    
    for desc_url, apply_url in job_urls:
        try:
            # Normalize URLs for deduplication
            normalized_desc_url = normalize_job_url(desc_url)
            if normalized_desc_url in processed_urls:
                continue
            processed_urls.add(normalized_desc_url)
            
            # Get job details based on job site
            job_details = None
            if job_site == JobSite.LEVER:
                job_details = get_lever_job_details(desc_url)
            elif job_site == JobSite.GREENHOUSE:
                job_details = get_greenhouse_job_details(desc_url)
            elif job_site == JobSite.ASHBY:
                job_details = get_ashby_job_details(desc_url)

            if not job_details:
                error_count += 1
                continue

            # Update URLs
            job_details["application_url"] = apply_url
            
            # Generate unique hash for the job
            job_hash = generate_job_hash(job_details)
            
            # Clean array fields for PostgreSQL
            if job_details.get("requirements"):
                job_details["requirements"] = "{" + ",".join('"' + str(req).replace('"', '\\"') + '"' for req in job_details["requirements"]) + "}"
            
            if job_details.get("qualifications"):
                job_details["qualifications"] = "{" + ",".join('"' + str(qual).replace('"', '\\"') + '"' for qual in job_details["qualifications"]) + "}"
            
            if job_details.get("benefits"):
                job_details["benefits"] = "{" + ",".join('"' + str(ben).replace('"', '\\"') + '"' for ben in job_details["benefits"]) + "}"
            
            if job_details.get("work_types"):
                job_details["work_types"] = "{" + ",".join(job_details["work_types"]) + "}" if job_details["work_types"] else "{remote}" if job_details.get("remote") else None

            # Map the job details to match our Supabase schema
            supabase_job = {
                "title": job_details["title"],
                "company": job_details["company"],
                "location": job_details["location"],
                "description": job_details["description"],
                "salary": job_details["salary"],
                "remote": job_details.get("remote", False),
                "work_types": job_details.get("work_types"),
                "employment_type": job_details.get("employment_type"),
                "experience_level": job_details.get("experience_level"),
                "requirements": job_details.get("requirements"),
                "qualifications": job_details.get("qualifications"),
                "benefits": job_details.get("benefits"),
                "application_url": job_details["application_url"],
                "company_logo": job_details.get("company_logo"),
                "source": job_details["source"],
                "posted_date": job_details["posted_date"],
                "expires_at": job_details["expires_at"],
                "scraped_at": datetime.now().isoformat(),
                "status": "active",
                "salary_min": job_details.get("salary_min"),
                "salary_max": job_details.get("salary_max"),
                "salary_currency": job_details.get("salary_currency"),
                "salary_type": job_details.get("salary_type"),
                "last_updated": datetime.now().isoformat(),
                "job_hash": job_hash
            }
            
            # Insert into Supabase
            try:
                data = supabase.table("jobs").insert(supabase_job).execute()
                processed_count += 1
                logging.info(f"Successfully inserted job: {job_details['title']} at {job_details['company']}")
            except Exception as e:
                error_count += 1
                logging.error(f"Error inserting job into Supabase: {str(e)}")
                
        except Exception as e:
            error_count += 1
            logging.error(f"Error processing job {desc_url}: {str(e)}")
            continue
            
    logging.info(f"Processed {processed_count} jobs with {error_count} errors")
    return processed_count, error_count
