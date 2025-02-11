from bs4 import BeautifulSoup
import requests
from utils.proxy import get_free_proxies
from utils.text_processor import TextProcessor
from enum import Enum
import yagooglesearch
import re
import logging
from datetime import datetime, timedelta
import hashlib


class JobSite(Enum):
    LEVER = "lever.co"
    GREENHOUSE = "boards.greenhouse.io/*/jobs/*"
    ASHBY = "ashbyhq.com"
    WELLFOUND = "wellfound.com"
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
            url = location_url if page == 1 else f"{location_url}?page={page}"
            response = requests.get(url)
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Find job links
            job_links = soup.find_all("a", href=lambda x: x and "/jobs/" in x)
            if not job_links:
                break
                
            # Extract and normalize URLs
            for link in job_links:
                href = link.get("href")
                if href:
                    if not href.startswith("http"):
                        href = "https://wellfound.com" + href
                    job_urls.append(href)
            
            # Check if there's a next page
            next_button = soup.find("a", string=lambda x: x and "Next" in x) or \
                         soup.find("button", string=lambda x: x and "Next" in x)
            if not next_button or "disabled" in next_button.get("class", []):
                break
                
            page += 1
            
        except Exception as e:
            logging.error(f"Error crawling Wellfound page {page}: {str(e)}")
            break
    
    return list(set(job_urls))  # Remove duplicates


def find_jobs(
    keyword: str,
    job_sites: list[JobSite],
    tbs: TBS | None,
    max_results: int = 200,
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
            if job_site == JobSite.WELLFOUND:
                job_urls_by_board[job_site] = crawl_wellfound_jobs(url)

    # Then do Google search for remaining job sites
    remaining_sites = [site for site in job_sites if site not in job_urls_by_board]
    if remaining_sites:
        proxies = [None] + get_free_proxies()
        proxy_index = 0

        success = False
        result = []

        while not success:
            try:
                proxy = proxies[proxy_index]
                proxy_index += 1

                if proxy_index >= len(proxies):
                    print("No more proxies to try.")
                    break
                search_sites = " OR ".join([f"site:{site.value}" for site in remaining_sites])
                search_query = f"{keyword} {search_sites}"
                print(f"Searching for {search_query} using proxy {proxy}")
                client = yagooglesearch.SearchClient(
                    search_query,
                    tbs=tbs.value if tbs else None,
                    max_search_result_urls_to_return=max_results,
                    proxy=proxy,
                    verbosity=0,
                )
                client.assign_random_user_agent()
                result = client.search()
                success = True
            except Exception as e:
                print(f"Error using proxy {proxy}: ", e)

        for job_site in remaining_sites:
            job_urls_for_job_site = [
                url for url in result if re.search(regex[job_site], url)
            ]
            cleaner = JobSearchResultCleaner(job_site)
            job_urls_by_board[job_site] = cleaner.clean(job_urls_for_job_site)

    return job_urls_by_board


def get_lever_job_details(link: str) -> dict:
    response = requests.get(link)
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

    # If no specific sections were found, try to extract from the main content
    if not any([requirements, qualifications, benefits]):
        main_content = soup.find("div", {"class": "content"}) or soup.find("div", {"class": "description"})
        if main_content:
            description = main_content.decode_contents()
            # Try to identify sections within the main content
            sections = main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5'])
            if sections:
                current_section = 'description'
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
                        
                        # Start new section
                        current_section = TextProcessor.identify_section(elem.get_text())
                        current_content = []
                    else:
                        current_content.append(str(elem))
            else:
                description_parts.append(TextProcessor.clean_html(description))

    # Combine description parts
    description = '\n\n'.join(description_parts)

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

    # Salary
    salary = None
    salary_min = None
    salary_max = None
    salary_currency = None
    salary_type = None
    
    # Look for salary in description and other elements
    salary_patterns = [
        r'\$\d{2,3}(?:,\d{3})*(?:\s*-\s*\$\d{2,3}(?:,\d{3})*)?(?:\s*k)?(?:\s*per\s*year)?',
        r'\$\d{2,3}(?:,\d{3})*(?:\s*k)?(?:\s*-\s*\$\d{2,3}(?:,\d{3})*(?:\s*k)?)?'
    ]
    
    compensation_elem = soup.find("div", {"class": "compensation"})
    salary_texts = [description, title, position]
    if compensation_elem:
        salary_texts.insert(0, compensation_elem.text)

    for pattern in salary_patterns:
        for text in salary_texts:
            if text:
                match = re.search(pattern, text)
                if match:
                    salary = match.group(0)
                    # Extract numbers
                    numbers = re.findall(r'\d+(?:,\d{3})*', salary)
                    if numbers:
                        salary_min = int(numbers[0].replace(',', ''))
                        if len(numbers) > 1:
                            salary_max = int(numbers[1].replace(',', ''))
                        salary_currency = '$'
                        if 'per year' in text.lower() or 'annually' in text.lower():
                            salary_type = 'yearly'
                        elif 'per hour' in text.lower() or 'hourly' in text.lower():
                            salary_type = 'hourly'
                        break

    # Experience Level
    experience_level = None
    experience_patterns = [
        (r'\b(?:senior|sr\.?\s*)\b', 'senior'),
        (r'\b(?:junior|jr\.?\s*)\b', 'junior'),
        (r'\b(?:mid-level|mid\s+level)\b', 'mid-level'),
        (r'\b(?:principal|staff|lead)\b', 'principal'),
        (r'\b(?:entry\s*-?\s*level|fresh\s*graduate|new\s*grad)\b', 'entry-level')
    ]
    
    for pattern, level in experience_patterns:
        if re.search(pattern, position.lower()) or re.search(pattern, description.lower()):
            experience_level = level
            break

    # Posted Date and Expiration
    posted_date = datetime.now().isoformat()  # Default to now if not found
    expires_at = (datetime.now() + timedelta(days=30)).isoformat()  # Default to 30 days from now

    # Try to find actual posted date
    for meta in soup.find_all("meta"):
        if meta.get("property") == "article:published_time":
            posted_date = meta.get("content")
            break

    # Create initial job details
    job_details = {
        "title": position,
        "company": company_name,
        "location": location,
        "description": description,
        "salary": salary,
        "remote": remote,
        "work_types": work_types,
        "employment_type": employment_type,
        "experience_level": experience_level,
        "requirements": requirements,
        "qualifications": qualifications,
        "benefits": benefits,
        "application_url": link,
        "company_logo": company_logo,
        "source": "lever",
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


def get_greenhouse_job_details(link: str) -> dict:
    response = requests.get(link)
    soup = BeautifulSoup(response.content, "html.parser")
    head = soup.find("head")

    # Basic job info with improved parsing
    title_elem = soup.find("h1")
    position = title_elem.text.strip() if title_elem else "Unknown"

    # Company info
    company_logo = None
    company_name = None
    
    # Try multiple ways to get company logo
    logo_elem = soup.find("img", {"class": "logo"}) or soup.find("img", {"alt": lambda x: x and "Logo" in x})
    if logo_elem and logo_elem.get("src"):
        company_logo = logo_elem["src"]
        if not company_logo.startswith("http"):
            company_logo = "https:" + company_logo if company_logo.startswith("//") else "https://" + company_logo

    # Try to get company name from URL first, then fallback to other methods
    company_match = re.search(r'boards\.greenhouse\.io/([^/]+)', link)
    if company_match:
        company_name = company_match.group(1).replace("-", " ").title()
        # Clean up common suffixes
        company_name = re.sub(r'(?i)(usa|inc|llc|corp)$', '', company_name).strip()
    
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
    texts_to_check = [location, description, position]
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

    # Create job details
    job_details = {
        "title": position,
        "company": company_name,
        "location": location,
        "description": description,
        "salary": salary,
        "remote": remote,
        "work_types": work_types,
        "employment_type": employment_type,
        "experience_level": experience_level,
        "requirements": requirements,
        "qualifications": qualifications,
        "benefits": benefits,
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
    response = requests.get(link)
    soup = BeautifulSoup(response.content, "html.parser")

    # Basic job info - Ashby uses specific data-testid attributes
    title_elem = soup.find("h1", {"data-testid": "job-title"}) or soup.find("h1")
    position = title_elem.text.strip() if title_elem else None

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
                current_content.append(str(elem))
        
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

    # Employment Type
    employment_type = None
    employment_elem = soup.find("div", {"data-testid": "job-type"})
    if employment_elem:
        employment_type = employment_elem.text.strip().lower()

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

    # Salary detection
    salary = None
    salary_min = None
    salary_max = None
    salary_currency = None
    salary_type = None
    
    # Look for salary in compensation section and description
    salary_elem = soup.find("div", {"data-testid": "compensation"})
    salary_texts = [description]
    if salary_elem:
        salary_texts.insert(0, salary_elem.text)

    salary_patterns = [
        r'\$\d{2,3}(?:,\d{3})*(?:\s*-\s*\$\d{2,3}(?:,\d{3})*)?(?:\s*k)?(?:\s*per\s*year)?',
        r'\$\d{2,3}(?:,\d{3})*(?:\s*k)?(?:\s*-\s*\$\d{2,3}(?:,\d{3})*(?:\s*k)?)?'
    ]

    for text in salary_texts:
        if not text:
            continue
        for pattern in salary_patterns:
            match = re.search(pattern, text)
            if match:
                salary = match.group(0)
                # Extract numbers
                numbers = re.findall(r'\d+(?:,\d{3})*', salary)
                if numbers:
                    salary_min = int(numbers[0].replace(',', ''))
                    if len(numbers) > 1:
                        salary_max = int(numbers[1].replace(',', ''))
                    salary_currency = '$'
                    if 'per year' in text.lower() or 'annually' in text.lower():
                        salary_type = 'yearly'
                    elif 'per hour' in text.lower() or 'hourly' in text.lower():
                        salary_type = 'hourly'
                    break
        if salary:
            break

    # Experience Level
    experience_level = None
    experience_patterns = [
        (r'\b(?:senior|sr\.?\s*|lead)\b', 'senior'),
        (r'\b(?:junior|jr\.?\s*)\b', 'junior'),
        (r'\b(?:mid[- ]level|mid\s+senior)\b', 'mid-level'),
        (r'\b(?:principal|staff|director)\b', 'principal'),
        (r'\b(?:entry[- ]level|fresh\s*graduate|new\s*grad)\b', 'entry-level')
    ]
    
    for pattern, level in experience_patterns:
        if re.search(pattern, position.lower() if position else '') or re.search(pattern, description.lower()):
            experience_level = level
            break

    # Posted Date and Expiration
    posted_date = datetime.now().isoformat()
    expires_at = (datetime.now() + timedelta(days=30)).isoformat()

    # Try to find actual posted date
    posted_date_elem = soup.find("div", {"data-testid": "job-posted-date"})
    if posted_date_elem:
        try:
            relative_date = posted_date_elem.text.strip()
            if "day" in relative_date:
                days = int(re.search(r'\d+', relative_date).group())
                posted_date = (datetime.now() - timedelta(days=days)).isoformat()
        except:
            pass

    # Create job details
    job_details = {
        "title": position,
        "company": company_name,
        "location": location,
        "description": description,
        "salary": salary,
        "remote": remote,
        "work_types": work_types,
        "employment_type": employment_type,
        "experience_level": experience_level,
        "requirements": requirements,
        "qualifications": [],  # Ashby typically combines requirements and qualifications
        "benefits": benefits,
        "application_url": link,
        "company_logo": company_logo,
        "source": "ashby",
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


def get_wellfound_job_details(link: str) -> dict:
    """Get job details from a Wellfound job posting."""
    response = requests.get(link)
    soup = BeautifulSoup(response.content, "html.parser")
    
    # Initialize job details
    job_details = {
        "title": "",
        "company": "",
        "company_logo": "",
        "location": "",
        "description": "",
        "requirements": "",
        "benefits": "",
        "salary": "",
        "employment_type": "",
        "work_types": [],
        "experience_level": "",
        "posted_date": datetime.now().isoformat(),
        "expiration_date": (datetime.now() + timedelta(days=30)).isoformat(),
        "apply_url": link,
        "source_url": link,
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
            
        # Extract location
        location_elem = soup.find("div", class_=lambda x: x and "location" in x.lower()) or \
                       soup.find("span", class_=lambda x: x and "location" in x.lower())
        if location_elem:
            location = location_elem.get_text().strip()
            job_details["location"] = location
            
            # Check for remote/hybrid indicators
            location_lower = location.lower()
            if "remote" in location_lower:
                job_details["work_types"].append("remote")
            if "hybrid" in location_lower:
                job_details["work_types"].append("hybrid")
            if not job_details["work_types"] and ("office" in location_lower or "on-site" in location_lower):
                job_details["work_types"].append("on-site")
                
        # Extract salary
        salary_elem = soup.find(string=lambda x: x and any(s in x.lower() for s in ["salary", "compensation"]))
        if salary_elem:
            parent = salary_elem.parent
            salary_text = parent.get_text() if parent else salary_elem
            # Extract salary range using regex
            salary_match = re.search(r'\$[\d,]+(?:\s*-\s*\$[\d,]+)?(?:\s*(?:k|K|thousand|million|M))?\s*(?:per\s*(?:year|month|week|hr|hour|annum|yr))?', salary_text)
            if salary_match:
                job_details["salary"] = salary_match.group(0)
                
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
        exp_elem = soup.find(string=lambda x: x and any(e in x.lower() for e in ["experience", "level", "seniority"]))
        if exp_elem:
            parent = exp_elem.parent
            if parent:
                exp_text = parent.get_text().lower()
                if any(level in exp_text for level in ["senior", "sr.", "lead"]):
                    job_details["experience_level"] = "senior"
                elif any(level in exp_text for level in ["mid", "intermediate"]):
                    job_details["experience_level"] = "mid"
                elif any(level in exp_text for level in ["junior", "jr.", "entry"]):
                    job_details["experience_level"] = "junior"
                    
        # Extract sections
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
            
            # Assign sections to job details
            for section, content in sections.items():
                job_details[section] = content
                
        # If no sections were found, try to get all content
        if not job_details["description"]:
            description_elems = main_content.find_all(["p", "ul", "ol"]) if main_content else []
            job_details["description"] = "\n".join(elem.get_text().strip() for elem in description_elems if elem.get_text().strip())
            
    except Exception as e:
        logging.error(f"Error parsing Wellfound job details from {link}: {str(e)}")
        
    return TextProcessor.process_job_details(job_details)


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
    unique_string = f"{job_details['company']}:{job_details['title']}:{job_details['location']}:{normalize_job_url(job_details['source_url'])}"
    # Create a hash of the string
    return hashlib.md5(unique_string.encode()).hexdigest()


def handle_job_insert(supabase: any, job_urls: list[tuple[str, str]], job_site: JobSite):
    """Handle job insertion with deduplication."""
    processed_urls = set()  # Track processed URLs
    
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
            elif job_site == JobSite.WELLFOUND:
                job_details = get_wellfound_job_details(desc_url)

            if not job_details:
                continue

            # Update URLs
            job_details["application_url"] = apply_url
            
            # Generate unique hash for the job
            job_hash = generate_job_hash(job_details)
            
            # Map the job details to match our Supabase schema
            supabase_job = {
                "title": job_details["title"],
                "company": job_details["company"],
                "location": job_details["location"],
                "description": job_details["description"],
                "salary": job_details["salary"],
                "remote": job_details["remote"],
                "work_types": "{" + ",".join(job_details["work_types"]) + "}" if job_details["work_types"] else "{remote}" if job_details["remote"] else None,
                "employment_type": job_details["employment_type"],
                "experience_level": job_details["experience_level"],
                "requirements": "{" + ",".join(job_details["requirements"]) + "}" if job_details["requirements"] else None,
                "qualifications": "{" + ",".join(f'"{q}"' for q in job_details["qualifications"]) + "}" if job_details["qualifications"] else None,
                "benefits": "{" + ",".join(f'"{b}"' for b in job_details["benefits"]) + "}" if job_details["benefits"] else None,
                "application_url": job_details["application_url"],
                "company_logo": job_details["company_logo"],
                "source": job_details["source"],
                "posted_date": job_details["posted_date"],
                "expires_at": job_details["expires_at"],
                "scraped_at": datetime.now().isoformat(),
                "status": "active",
                "salary_min": job_details["salary_min"],
                "salary_max": job_details["salary_max"],
                "salary_currency": job_details["salary_currency"],
                "salary_type": job_details["salary_type"],
                "last_updated": datetime.now().isoformat(),
                "job_hash": job_hash
            }

            print(f"Processing job from {job_site.name}: {supabase_job['title']} at {supabase_job['company']}")
            
            # Try to upsert the job based on job_hash
            supabase.upsert_job(supabase_job)
            
        except Exception as e:
            logging.error(f"Failed to process job {desc_url}: {str(e)}")
            continue


regex = {
    JobSite.LEVER: r"https://jobs.lever.co/[^/]+/[^/]+(?:/apply)?",
    JobSite.GREENHOUSE: r"https?://(?:job-boards\.|boards\.)?greenhouse\.io/[^/]+/jobs/\d+(?:[#?][^/]*)?",
    JobSite.ASHBY: r"https?://jobs\.ashbyhq\.com/[^/]+/[a-f0-9-]+(?:/application)?",
    JobSite.WELLFOUND: r"https?://(?:www\.)?wellfound\.com/jobs?/[^/]+/[^/]+(?:/apply)?",
    JobSite.ANGELLIST: "TODO",
    JobSite.WORKABLE: "TODO",
    JobSite.INDEED: "TODO",
    JobSite.GLASSDOOR: "TODO",
    JobSite.LINKEDIN: "TODO",
    JobSite.CUSTOM: r"https://[^/]+/(?:company/)?(?:careers|jobs)/.*"
}


class JobSearchResultCleaner:

    def __init__(self, job_site: JobSite):
        self.job_site = job_site

    def _prune_urls(self, urls: list[str]) -> list[str]:
        pruned_urls = []
        for url in urls:
            if self.job_site == JobSite.GREENHOUSE:
                # Handle various Greenhouse URL formats
                match = re.search(regex[self.job_site], url)
                if match:
                    url = match.group()
                    # Extract the job ID from URL or query parameter
                    job_id = None
                    gh_jid_match = re.search(r'gh_jid=(\d+)', url)
                    if gh_jid_match:
                        job_id = gh_jid_match.group(1)
                    else:
                        job_id_match = re.search(r'/jobs/(\d+)', url)
                        if job_id_match:
                            job_id = job_id_match.group(1)
                    
                    if job_id:
                        # Extract company name
                        company_match = re.search(r'(?:job-boards\.|boards\.)?greenhouse\.io/([^/]+)', url)
                        if company_match:
                            company = company_match.group(1)
                            # Normalize to standard format
                            url = f"https://boards.greenhouse.io/{company}/jobs/{job_id}"
                            pruned_urls.append(url)
            else:
                # Handle other job sites as before
                match = re.search(regex[self.job_site], url)
                if match:
                    pruned_urls.append(match.group())
        return pruned_urls

    def _remove_duplicates(self, urls: list[str]) -> list[str]:
        return list(set(urls))

    def _make_direct_apply_urls(self, urls: list[str]) -> list[tuple[str, str]]:
        """Returns a list of tuples (description_url, apply_url)"""
        if self.job_site == JobSite.LEVER:
            urls = [re.sub(r"\?.*", "", url) for url in urls]  # clean query parameters
            return [(url, url + "/apply") for url in urls]
        
        if self.job_site == JobSite.GREENHOUSE:
            cleaned_urls = []
            apply_urls = []
            for url in urls:
                # Extract company and job ID
                company_match = re.search(r'boards\.greenhouse\.io/([^/]+)', url)
                job_id_match = re.search(r'/jobs/(\d+)', url)
                
                if company_match and job_id_match:
                    company = company_match.group(1)
                    job_id = job_id_match.group(1)
                    # Use the standard format for description URL
                    desc_url = f"https://boards.greenhouse.io/{company}/jobs/{job_id}"
                    # Create the apply URL
                    apply_url = f"https://boards.greenhouse.io/embed/job_app?for={company}&token={job_id}"
                    
                    cleaned_urls.append(desc_url)
                    apply_urls.append(apply_url)
            
            return list(zip(cleaned_urls, apply_urls))
        
        if self.job_site == JobSite.ASHBY:
            urls = [re.sub(r"\?.*", "", url) for url in urls]
            return [(url, url + "/application?embed=js") for url in urls]
        
        return [(url, url) for url in urls]  # Default to same URL for both

    def clean(self, job_search_result: list) -> list[tuple[str, str]]:
        """Clean the job search result to return tuples of (description_url, apply_url)."""
        if not job_search_result:
            return []
        try:
            return self._make_direct_apply_urls(
                self._remove_duplicates(self._prune_urls(job_search_result))
            )
        except Exception as e:
            print(f"Error cleaning job search result: {e}")
            return []
