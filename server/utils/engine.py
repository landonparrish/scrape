from bs4 import BeautifulSoup
import requests
from utils.proxy import get_free_proxies
from enum import Enum
import yagooglesearch
import re
import logging
from datetime import datetime, timedelta


class JobSite(Enum):
    LEVER = "lever.co"
    GREENHOUSE = "boards.greenhouse.io/*/jobs/*"
    ASHBY = "ashbyhq.com"
    ANGELLIST = "TODO"
    WORKABLE = "TODO"
    INDEED = "TODO"
    GLASSDOOR = "TODO"
    LINKEDIN = "TODO"
    


class TBS(Enum):
    PAST_TWELVE_HOURS = "qdr:h12"
    PAST_DAY = "qdr:d"
    PAST_WEEK = "qdr:w"
    PAST_MONTH = "qdr:m"
    PAST_YEAR = "qdr:y"


def find_jobs(
    keyword: str,
    job_sites: list[JobSite],
    tbs: TBS | None,
    max_results: int = 200,
):
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
            search_sites = " OR ".join([f"site:{site.value}" for site in job_sites])
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

    job_urls_by_board = {}
    for job_site in job_sites:
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

    # Description
    description_elem = soup.find("div", {"class": "content"}) or soup.find("div", {"class": "description"})
    description = description_elem.decode_contents() if description_elem else ""

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

    # Requirements and Qualifications
    requirements = []
    qualifications = []
    for section in soup.find_all(["h3", "h4"]):
        if any(keyword in section.text.lower() for keyword in ["requirements", "qualifications", "what you'll need"]):
            items = []
            current = section.find_next()
            while current and current.name in ["p", "li", "ul"]:
                if current.name == "li":
                    items.append(current.text.strip())
                elif current.name == "ul":
                    for li in current.find_all("li"):
                        items.append(li.text.strip())
                current = current.find_next()
            if "requirements" in section.text.lower():
                requirements.extend(items)
            else:
                qualifications.extend(items)

    # Benefits
    benefits = []
    for section in soup.find_all(["h3", "h4"]):
        if any(keyword in section.text.lower() for keyword in ["benefits", "perks", "what we offer"]):
            items = []
            current = section.find_next()
            while current and current.name in ["p", "li", "ul"]:
                if current.name == "li":
                    items.append(current.text.strip())
                elif current.name == "ul":
                    for li in current.find_all("li"):
                        items.append(li.text.strip())
                current = current.find_next()
            benefits.extend(items)

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

    return {
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


def get_greenhouse_job_details(link: str) -> dict:
    response = requests.get(link)
    soup = BeautifulSoup(response.content, "html.parser")
    head = soup.find("head")
    content = soup.find("div", {"id": "content"})

    # Basic job info
    position = (
        head.find("meta", property="og:title")["content"]
        if head.find("meta", property="og:title")
        else "Unknown"
    )

    company_logo = (
        head.find("meta", property="og:image")["content"]
        if head.find("meta", property="og:image")
        else None
    )

    title = soup.title.string if soup.title else "Unknown"
    company_name = title.split(" at ")[1].strip() if " at " in title else title.strip()

    # Location
    location_elem = soup.find("div", {"class": "location"})
    location = location_elem.text.strip() if location_elem else ""

    # Description
    description_elem = soup.find("div", {"id": "content"})
    description = description_elem.decode_contents() if description_elem else ""

    # Employment Type
    employment_type = "full-time"  # Default
    for p in soup.find_all("p"):
        if "type:" in p.text.lower():
            employment_type = p.text.split(":")[-1].strip().lower()

    # Remote Status
    remote = False
    if location and any(keyword in location.lower() for keyword in ["remote", "hybrid"]):
        remote = True

    # Requirements and Qualifications
    requirements = []
    qualifications = []
    for section in soup.find_all(["h2", "h3"]):
        if any(keyword in section.text.lower() for keyword in ["requirements", "qualifications", "what you'll need"]):
            items = []
            current = section.find_next()
            while current and current.name in ["p", "li", "ul"]:
                if current.name == "li":
                    items.append(current.text.strip())
                elif current.name == "ul":
                    for li in current.find_all("li"):
                        items.append(li.text.strip())
                current = current.find_next()
            if "requirements" in section.text.lower():
                requirements.extend(items)
            else:
                qualifications.extend(items)

    # Benefits
    benefits = []
    for section in soup.find_all(["h2", "h3"]):
        if any(keyword in section.text.lower() for keyword in ["benefits", "perks", "what we offer"]):
            items = []
            current = section.find_next()
            while current and current.name in ["p", "li", "ul"]:
                if current.name == "li":
                    items.append(current.text.strip())
                elif current.name == "ul":
                    for li in current.find_all("li"):
                        items.append(li.text.strip())
                current = current.find_next()
            benefits.extend(items)

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
    
    for pattern in salary_patterns:
        for text in [description, title, position]:
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

    # Work Types (e.g., on-site, hybrid, remote)
    work_types = []
    if "remote" in location.lower() or "remote" in description.lower():
        work_types.append("remote")
    if "hybrid" in location.lower() or "hybrid" in description.lower():
        work_types.append("hybrid")
    if "on-site" in location.lower() or "on site" in description.lower() or "onsite" in description.lower():
        work_types.append("on-site")

    # Posted Date and Expiration
    posted_date = datetime.now().isoformat()  # Default to now if not found
    expires_at = (datetime.now() + timedelta(days=30)).isoformat()  # Default to 30 days from now

    # Try to find actual posted date
    for meta in head.find_all("meta"):
        if meta.get("property") == "article:published_time":
            posted_date = meta.get("content")
            break

    return {
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


def get_ashby_job_details(link: str) -> dict:
    response = requests.get(link)
    soup = BeautifulSoup(response.content, "html.parser")
    head = soup.find("head")

    # Basic job info
    title = head.find("title").string if head.find("title") else "Unknown"
    company_name = title.split(" @ ")[1].strip() if " @ " in title else title.strip()
    position = title.split(" @ ")[0].strip() if " @ " in title else "Unknown"

    # Company Logo
    company_logo = (
        head.find("meta", property="og:image")["content"]
        if head.find("meta", property="og:image")
        else None
    )

    # Location
    location = ""
    location_elem = soup.find("div", {"data-testid": "job-location"})
    if location_elem:
        location = location_elem.text.strip()

    # Description
    description = ""
    description_elem = soup.find("div", {"data-testid": "job-description"})
    if description_elem:
        description = description_elem.decode_contents()

    # Employment Type
    employment_type = "full-time"  # Default
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
            if "remote" in text.lower():
                remote = True
                if "remote" not in work_types:
                    work_types.append("remote")
            if "hybrid" in text.lower() and "hybrid" not in work_types:
                work_types.append("hybrid")
            if any(x in text.lower() for x in ["on-site", "onsite", "in office"]) and "on-site" not in work_types:
                work_types.append("on-site")

    # Requirements and Qualifications
    requirements = []
    qualifications = []
    for section in soup.find_all(["h2", "h3", "h4"]):
        if any(keyword in section.text.lower() for keyword in ["requirements", "qualifications", "what you'll need"]):
            items = []
            current = section.find_next()
            while current and current.name in ["p", "li", "ul"]:
                if current.name == "li":
                    items.append(current.text.strip())
                elif current.name == "ul":
                    for li in current.find_all("li"):
                        items.append(li.text.strip())
                current = current.find_next()
            if "requirements" in section.text.lower():
                requirements.extend(items)
            else:
                qualifications.extend(items)

    # Benefits
    benefits = []
    for section in soup.find_all(["h2", "h3", "h4"]):
        if any(keyword in section.text.lower() for keyword in ["benefits", "perks", "what we offer"]):
            items = []
            current = section.find_next()
            while current and current.name in ["p", "li", "ul"]:
                if current.name == "li":
                    items.append(current.text.strip())
                elif current.name == "ul":
                    for li in current.find_all("li"):
                        items.append(li.text.strip())
                current = current.find_next()
            benefits.extend(items)

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
    
    salary_elem = soup.find("div", {"data-testid": "compensation"})
    salary_texts = [description, title, position]
    if salary_elem:
        salary_texts.insert(0, salary_elem.text)

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
    posted_date_elem = soup.find("div", {"data-testid": "job-posted-date"})
    if posted_date_elem:
        try:
            # Ashby usually shows relative dates like "2 days ago"
            relative_date = posted_date_elem.text.strip()
            if "day" in relative_date:
                days = int(re.search(r'\d+', relative_date).group())
                posted_date = (datetime.now() - timedelta(days=days)).isoformat()
        except:
            pass

    return {
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


def handle_job_insert(supabase: any, job_urls: list[str], job_site: JobSite):
    for link in job_urls:
        try:
            job_details = None
            if job_site == JobSite.LEVER:
                job_details = get_lever_job_details(link)
            elif job_site == JobSite.GREENHOUSE:
                job_details = get_greenhouse_job_details(link)
            elif job_site == JobSite.ASHBY:
                job_details = get_ashby_job_details(link)

            if not job_details:
                continue

            # Map the job details to match our Supabase schema
            supabase_job = {
                "title": job_details["title"],
                "company": job_details["company"],
                "location": job_details["location"],
                "description": job_details["description"],
                "salary": job_details["salary"],
                "remote": job_details["remote"],
                "work_types": "{" + ",".join(job_details["work_types"]) + "}" if job_details["work_types"] else "{remote}" if job_details["remote"] else None,
                "employment_type": None,  # Set to null as it has constraints
                "experience_level": None,  # Set to null to avoid constraint issues
                "requirements": "{" + ",".join(job_details["requirements"]) + "}" if job_details["requirements"] else None,
                "qualifications": "{" + ",".join(f'"{q}"' for q in job_details["qualifications"]) + "}" if job_details["qualifications"] else None,
                "benefits": "{" + ",".join(f'"{b}"' for b in job_details["benefits"]) + "}" if job_details["benefits"] else None,
                "application_url": job_details["application_url"],
                "company_logo": job_details["company_logo"],
                "source": None,  # Set to null to avoid constraint issues
                "posted_date": job_details["posted_date"],
                "expires_at": job_details["expires_at"],
                "scraped_at": datetime.now().isoformat(),
                "status": "active",
                "salary_min": job_details["salary_min"],
                "salary_max": job_details["salary_max"],
                "salary_currency": job_details["salary_currency"],
                "salary_type": job_details["salary_type"],
                "last_updated": datetime.now().isoformat()
            }

            print(f"Inserting job from {job_site.name}: {supabase_job['title']} at {supabase_job['company']}")
            supabase.insert_job(supabase_job)
        except Exception as e:
            logging.error(f"Failed to process job {link}: {str(e)}")
            continue


regex = {
    JobSite.LEVER: r"https://jobs.lever.co/[^/]+/[^/]+",
    JobSite.GREENHOUSE: r"https://boards.greenhouse.io/[^/]+/jobs/[^/]+",
    JobSite.ANGELLIST: "TODO",
    JobSite.WORKABLE: "TODO",
    JobSite.INDEED: "TODO",
    JobSite.GLASSDOOR: "TODO",
    JobSite.LINKEDIN: "TODO",
    JobSite.ASHBY: r"https://jobs.ashbyhq.com/[^/]+/[^/]+",
}


class JobSearchResultCleaner:

    def __init__(self, job_site: JobSite):
        self.job_site = job_site

    def _prune_urls(self, urls: list[str]) -> list[str]:
        return [
            re.search(regex[self.job_site], url).group()
            for url in urls
            if re.search(regex[self.job_site], url)
        ]

    def _remove_duplicates(self, urls: list[str]) -> list[str]:
        return list(set(urls))

    def _make_direct_apply_urls(self, urls: list[str]) -> list[str]:
        if self.job_site == JobSite.LEVER:
            urls = [re.sub(r"\?.*", "", url) for url in urls]
            # clean the url of all query parameters
            return [url + "/apply" for url in urls]
        if self.job_site == JobSite.GREENHOUSE:
            cleaned_urls = [re.sub(r"\?.*", "", url) for url in urls]
            urls = [
                re.sub(
                    r"https://boards.greenhouse.io/([^/]+)/jobs/([^/]+)",
                    r"https://boards.greenhouse.io/embed/job_app?for=\1&token=\2",
                    url,
                )
                for url in cleaned_urls
            ]
            return urls
        if self.job_site == JobSite.ASHBY:
            urls = [re.sub(r"\?.*", "", url) for url in urls]
            return [url + "/application?embed=js" for url in urls]
        
        return urls

    def clean(self, job_search_result: list) -> list[str]:
        """Clean the job search result to only include valid job URLs."""
        if not job_search_result:
            return []
        try:
            return self._make_direct_apply_urls(
                self._remove_duplicates(self._prune_urls(job_search_result))
            )
        except Exception as e:
            print(f"Error cleaning job search result: {e}")
            return []
