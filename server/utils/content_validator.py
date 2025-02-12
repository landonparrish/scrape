from bs4 import BeautifulSoup
import re
import logging
from typing import Dict, List, Optional
import json

class ContentValidator:
    def __init__(self):
        # Common patterns that indicate invalid or blocked content
        self.invalid_patterns = [
            r'access denied',
            r'rate limit',
            r'too many requests',
            r'blocked',
            r'captcha',
            r'security check',
            r'verify you are human',
            r'automated access',
            r'suspicious activity'
        ]
        
        # Required elements for different page types
        self.required_elements = {
            'company': {
                'selectors': ['header', 'nav', 'footer'],
                'min_content_length': 1000
            },
            'listing': {
                'selectors': ['div', 'ul', 'a'],
                'min_content_length': 500
            },
            'detail': {
                'selectors': ['h1', 'div', 'form'],
                'min_content_length': 200
            }
        }
        
        # Job board specific patterns
        self.job_board_patterns = {
            'lever.co': {
                'title': r'<h2[^>]*class="[^"]*posting-headline[^"]*"[^>]*>',
                'company': r'<img[^>]*class="[^"]*main-header-logo[^"]*"[^>]*>',
                'content': r'<div[^>]*class="[^"]*posting-content[^"]*"[^>]*>'
            },
            'greenhouse.io': {
                'title': r'<h1[^>]*class="[^"]*app-title[^"]*"[^>]*>',
                'company': r'<div[^>]*class="[^"]*company-name[^"]*"[^>]*>',
                'content': r'<div[^>]*id="content"[^>]*>'
            },
            'ashbyhq.com': {
                'title': r'<h1[^>]*class="[^"]*job-title[^"]*"[^>]*>',
                'company': r'<div[^>]*class="[^"]*company-info[^"]*"[^>]*>',
                'content': r'<div[^>]*class="[^"]*job-description[^"]*"[^>]*>'
            }
        }

    def validate_response(self, response, expected_type: str) -> bool:
        """Validate response content."""
        try:
            # Check status code
            if response.status_code != 200:
                return False
                
            # Check content type
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type.lower():
                return False
                
            # Get content
            content = response.text
            if not content:
                return False
                
            # Check for invalid patterns
            if self._has_invalid_patterns(content):
                return False
                
            # Parse HTML
            soup = BeautifulSoup(content, 'html.parser')
            
            # Check for basic HTML structure
            if not self._has_valid_structure(soup):
                return False
                
            # Check for required elements
            if not self._has_required_elements(soup, expected_type):
                return False
                
            # Check for job board specific patterns
            if not self._validate_job_board_content(content, response.url):
                return False
                
            # Validate content integrity
            if not self._validate_content_integrity(soup, expected_type):
                return False
                
            return True
            
        except Exception as e:
            logging.error(f"Error validating response: {str(e)}")
            return False

    def _has_invalid_patterns(self, content: str) -> bool:
        """Check if content contains any invalid patterns."""
        content_lower = content.lower()
        return any(pattern.lower() in content_lower for pattern in self.invalid_patterns)

    def _has_valid_structure(self, soup: BeautifulSoup) -> bool:
        """Check if HTML has valid basic structure."""
        # Must have html, head, and body tags
        if not (soup.html and soup.head and soup.body):
            return False
            
        # Must have title tag
        if not soup.title:
            return False
            
        # Must have at least one meta tag
        if not soup.find('meta'):
            return False
            
        return True

    def _has_required_elements(self, soup: BeautifulSoup, page_type: str) -> bool:
        """Check if page has required elements for its type."""
        requirements = self.required_elements.get(page_type, {})
        
        # Check for required selectors
        for selector in requirements.get('selectors', []):
            if not soup.find(selector):
                return False
                
        # Check content length
        min_length = requirements.get('min_content_length', 0)
        if len(soup.get_text()) < min_length:
            return False
            
        return True

    def _validate_job_board_content(self, content: str, url: str) -> bool:
        """Validate content against job board specific patterns."""
        # Determine which job board
        board_patterns = None
        for board, patterns in self.job_board_patterns.items():
            if board in url:
                board_patterns = patterns
                break
                
        if not board_patterns:
            return True  # No specific patterns to check
            
        # Check for required patterns
        return all(
            re.search(pattern, content, re.IGNORECASE)
            for pattern in board_patterns.values()
        )

    def _validate_content_integrity(self, soup: BeautifulSoup, page_type: str) -> bool:
        """Validate the integrity and completeness of the content."""
        if page_type == 'detail':
            # Job details should have title, description, and some way to apply
            if not (
                soup.find(['h1', 'h2'], string=re.compile(r'.+')) and  # Non-empty title
                soup.find(['div', 'p'], string=re.compile(r'.{200,}')) and  # Description with minimum length
                (
                    soup.find('a', string=re.compile(r'apply|submit|send', re.I)) or
                    soup.find('button', string=re.compile(r'apply|submit|send', re.I)) or
                    soup.find('form')
                )
            ):
                return False
                
        elif page_type == 'listing':
            # Listings should have multiple job entries
            job_links = soup.find_all('a', href=True)
            job_links = [link for link in job_links if 'job' in link.get('href', '').lower()]
            if len(job_links) < 2:  # Expect at least 2 jobs in a listing
                return False
                
        elif page_type == 'company':
            # Company pages should have company info
            if not (
                soup.find(['h1', 'h2'], string=re.compile(r'.+')) and  # Company name
                (
                    soup.find('img', {'src': True}) or  # Logo
                    soup.find(['div', 'p'], string=re.compile(r'.{100,}'))  # Company description
                )
            ):
                return False
                
        return True 