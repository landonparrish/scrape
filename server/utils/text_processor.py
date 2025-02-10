from bs4 import BeautifulSoup
import re
from typing import List, Optional, Dict

class TextProcessor:
    # Section identifiers for better content detection
    SECTION_IDENTIFIERS = {
        'requirements': [
            'requirements', 'what you\'ll need', 'qualifications',
            'key skills', 'must have', 'required skills',
            'technical requirements', 'minimum qualifications',
            'basic qualifications', 'essential skills'
        ],
        'benefits': [
            'benefits', 'perks', 'what we offer', 'why join us',
            'compensation', 'what\'s in it for you', 'rewards',
            'total compensation', 'package includes', 'we provide'
        ]
    }

    # Technology terms to preserve case
    TECH_TERMS = {
        'API', 'AWS', 'REST', 'SQL', 'UI', 'UX', 'HTML', 'CSS', 'JS',
        'JavaScript', 'Python', 'React', 'Node.js', 'TypeScript', 'Vue',
        'Angular', 'Docker', 'Kubernetes', 'Git', 'CI/CD', 'DevOps'
    }

    @staticmethod
    def identify_section(text: str) -> str:
        """Identify which section a text belongs to based on keywords."""
        text_lower = text.lower()
        for section, identifiers in TextProcessor.SECTION_IDENTIFIERS.items():
            if any(identifier in text_lower for identifier in identifiers):
                return section
        return 'other'

    @staticmethod
    def clean_html(html_content: str) -> str:
        """Remove HTML tags while preserving structure."""
        if not html_content:
            return ""
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for element in soup(['script', 'style']):
            element.decompose()
        
        # Preserve code blocks
        for code in soup.find_all(['code', 'pre']):
            code.replace_with(f"\n```\n{code.get_text()}\n```\n")
            
        # Convert links to text with URL
        for link in soup.find_all('a'):
            href = link.get('href', '')
            if href and not href.startswith('#'):
                link.replace_with(f"{link.get_text()} ({href})")
        
        # Convert lists to bullet points
        for ul in soup.find_all(['ul', 'ol']):
            for li in ul.find_all('li'):
                li.replace_with(f"\n• {li.get_text()}")
            
        # Preserve paragraph structure
        for p in soup.find_all('p'):
            p.replace_with(f"\n\n{p.get_text()}\n\n")
            
        # Get text and clean whitespace
        text = soup.get_text()
        
        # Normalize whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        return text.strip()

    @staticmethod
    def title_case(text: str) -> str:
        """Convert text to Title Case while preserving technical terms."""
        if not text:
            return ""
        
        words = text.split()
        titled_words = []
        
        for word in words:
            if word.upper() in TextProcessor.TECH_TERMS:
                titled_words.append(word.upper())
            elif word in TextProcessor.TECH_TERMS:
                titled_words.append(word)  # Keep original casing for known tech terms
            else:
                titled_words.append(word.capitalize())
                
        return ' '.join(titled_words)

    @staticmethod
    def sentence_case(text: str) -> str:
        """Convert text to Sentence case while preserving common acronyms."""
        if not text:
            return ""
            
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        processed_sentences = []
        
        for sentence in sentences:
            if sentence:
                # Capitalize first letter
                processed = sentence[0].upper() + sentence[1:] if len(sentence) > 1 else sentence.upper()
                processed_sentences.append(processed)
                
        return ' '.join(processed_sentences)

    @staticmethod
    def extract_bullet_points(text: str) -> List[str]:
        """Extract bullet points from text into a list."""
        if not text:
            return []
            
        # Split by bullet points and clean
        points = [p.strip() for p in text.split('•') if p.strip()]
        return points

    @staticmethod
    def clean_requirements(requirements: List[str]) -> List[str]:
        """Clean and standardize requirement items."""
        cleaned = []
        for req in requirements:
            # Remove common prefixes
            req = re.sub(r'^[-•*]\s*', '', req)
            # Standardize education requirements
            req = re.sub(r'B\.?S\.?/M\.?S\.?', "Bachelor's or Master's degree", req, flags=re.IGNORECASE)
            req = re.sub(r'B\.?S\.?', "Bachelor's degree", req, flags=re.IGNORECASE)
            req = re.sub(r'M\.?S\.?', "Master's degree", req, flags=re.IGNORECASE)
            # Clean whitespace
            req = re.sub(r'\s+', ' ', req).strip()
            if req:
                cleaned.append(req)
        return list(dict.fromkeys(cleaned))  # Remove duplicates while preserving order

    @staticmethod
    def clean_benefits(benefits: List[str]) -> List[str]:
        """Clean and standardize benefit items."""
        cleaned = []
        for benefit in benefits:
            # Remove common prefixes
            benefit = re.sub(r'^[-•*]\s*', '', benefit)
            # Clean whitespace
            benefit = re.sub(r'\s+', ' ', benefit).strip()
            if benefit:
                cleaned.append(benefit)
        return list(dict.fromkeys(cleaned))  # Remove duplicates while preserving order

    @staticmethod
    def clean_location(location: str) -> str:
        """Clean and normalize location text."""
        if not location:
            return ""
        
        # Standardize separators
        location = re.sub(r'\s*[/,]\s*', ', ', location)
        
        # Handle remote indicators
        location = re.sub(r'remote( work)?', 'Remote', location, flags=re.IGNORECASE)
        location = re.sub(r'work from home', 'Remote', location, flags=re.IGNORECASE)
        
        # Standardize common terms
        location = re.sub(r'hybrid( work)?', 'Hybrid', location, flags=re.IGNORECASE)
        
        # Clean whitespace
        location = re.sub(r'\s+', ' ', location).strip()
        
        return TextProcessor.title_case(location)

    @staticmethod
    def process_job_field(field_name: str, content: str) -> str:
        """Process different job fields according to their specific requirements."""
        if not content:
            return ""
            
        # Clean HTML first
        cleaned_text = TextProcessor.clean_html(content)
        
        # Apply field-specific processing
        if field_name in ['benefits', 'company', 'title']:
            return TextProcessor.title_case(cleaned_text)
        elif field_name in ['requirements', 'qualifications', 'description']:
            return TextProcessor.sentence_case(cleaned_text)
        elif field_name == 'location':
            return TextProcessor.clean_location(cleaned_text)
        else:
            return cleaned_text

    @staticmethod
    def process_job_details(job_details: dict) -> dict:
        """Process all job details fields with enhanced cleaning."""
        processed = {}
        
        for field, content in job_details.items():
            if isinstance(content, str):
                processed[field] = TextProcessor.process_job_field(field, content)
            elif isinstance(content, list):
                if field == 'requirements':
                    processed[field] = TextProcessor.clean_requirements(content)
                elif field == 'benefits':
                    processed[field] = TextProcessor.clean_benefits(content)
                else:
                    processed[field] = content
            else:
                processed[field] = content
                
        return processed 