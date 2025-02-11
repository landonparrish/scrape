from bs4 import BeautifulSoup
import re
from typing import List, Optional, Dict

class TextProcessor:
    # Enhanced section identifiers for better content detection
    SECTION_IDENTIFIERS = {
        'summary': [
            'about the role', 'overview', 'position summary', 'job summary',
            'role overview', 'the opportunity', 'position overview',
            'what you\'ll do', 'responsibilities', 'the role'
        ],
        'requirements': [
            'requirements', 'what you\'ll need', 'qualifications',
            'key skills', 'must have', 'required skills',
            'technical requirements', 'minimum qualifications',
            'basic qualifications', 'essential skills',
            'what we\'re looking for', 'who you are'
        ],
        'qualifications': [
            'preferred qualifications', 'nice to have', 'desired skills',
            'additional qualifications', 'preferred skills',
            'bonus points', 'ideal candidate', 'great if you have'
        ],
        'benefits': [
            'benefits', 'perks', 'what we offer', 'why join us',
            'compensation', 'what\'s in it for you', 'rewards',
            'total compensation', 'package includes', 'we provide',
            'why work here', 'what you\'ll get'
        ]
    }

    # Technology terms to preserve case
    TECH_TERMS = {
        'API', 'AWS', 'REST', 'SQL', 'UI', 'UX', 'HTML', 'CSS', 'JS',
        'JavaScript', 'Python', 'React', 'Node.js', 'TypeScript', 'Vue',
        'Angular', 'Docker', 'Kubernetes', 'Git', 'CI/CD', 'DevOps'
    }

    @staticmethod
    def identify_section(text: str, content: str = None) -> str:
        """
        Identify which section a text belongs to based on keywords and content analysis.
        Now also looks at the content following the header for additional context.
        """
        text_lower = text.lower()
        
        # First try direct matches
        for section, identifiers in TextProcessor.SECTION_IDENTIFIERS.items():
            if any(identifier in text_lower for identifier in identifiers):
                return section
                
        # If content is provided, use it for additional context
        if content:
            content_lower = content.lower()
            # Look for requirement indicators in content
            if any(word in content_lower for word in ['required', 'must have', 'essential']):
                return 'requirements'
            # Look for qualification indicators
            if any(word in content_lower for word in ['preferred', 'nice to have', 'ideal']):
                return 'qualifications'
            # Look for benefit indicators
            if any(word in content_lower for word in ['offer', 'provide', 'package', 'compensation']):
                return 'benefits'
                
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
        """Enhanced bullet point extraction with better cleaning."""
        if not text:
            return []
        
        # Split by common bullet point indicators
        points = []
        
        # First try to split by HTML list items
        soup = BeautifulSoup(text, 'html.parser')
        li_items = soup.find_all('li')
        if li_items:
            points.extend([item.get_text().strip() for item in li_items])
        else:
            # If no HTML lists, try other bullet point patterns
            bullet_patterns = [
                r'[•●■◆▪️-]\s*([^•●■◆▪️-][^\n]+)',  # Common bullet points
                r'^\s*\d+\.\s+([^\n]+)',  # Numbered lists
                r'^\s*[A-Za-z]\)\s+([^\n]+)',  # Letter lists
                r'(?m)^\s*[-*]\s+([^\n]+)'  # Markdown-style lists
            ]
            
            for pattern in bullet_patterns:
                matches = re.finditer(pattern, text, re.MULTILINE)
                points.extend([match.group(1).strip() for match in matches])
        
        # Clean and normalize points
        cleaned_points = []
        for point in points:
            # Remove any remaining bullet points or numbers
            point = re.sub(r'^(?:\d+\.|[•●■◆▪️-]|\([A-Za-z]\))\s*', '', point)
            # Clean whitespace
            point = ' '.join(point.split())
            if point and len(point) > 5:  # Only keep substantial points
                cleaned_points.append(point)
                
        return list(dict.fromkeys(cleaned_points))  # Remove duplicates while preserving order

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
    def summarize_text(text: str, max_length: int = 500) -> str:
        """
        Summarize text by extracting key sentences.
        This is a simple extractive summarization - we could replace this with an LLM call.
        """
        if not text or len(text) <= max_length:
            return text
            
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Score sentences based on importance indicators
        scored_sentences = []
        important_phrases = [
            'responsible for', 'will be', 'looking for',
            'role involves', 'position requires', 'you\'ll be',
            'key responsibilities', 'main duties'
        ]
        
        for sentence in sentences:
            score = 0
            # Longer sentences likely contain more information
            score += min(len(sentence.split()), 20) * 0.1
            # Sentences with important phrases score higher
            score += sum(2 for phrase in important_phrases if phrase in sentence.lower())
            # First and last sentences often contain key information
            if sentence == sentences[0]:
                score += 3
            elif sentence == sentences[-1]:
                score += 1
            
            scored_sentences.append((score, sentence))
            
        # Sort by score and take top sentences
        scored_sentences.sort(reverse=True)
        summary = []
        current_length = 0
        
        for _, sentence in scored_sentences:
            if current_length + len(sentence) > max_length:
                break
            summary.append(sentence)
            current_length += len(sentence)
            
        return ' '.join(summary)

    @staticmethod
    def process_job_details(job_details: dict) -> dict:
        """Enhanced job details processing with better section handling and summarization."""
        processed = {}
        
        for field, content in job_details.items():
            if isinstance(content, str):
                if field == 'description':
                    # Summarize the description
                    processed[field] = TextProcessor.summarize_text(content)
                else:
                    processed[field] = TextProcessor.process_job_field(field, content)
            elif isinstance(content, list):
                if field in ['requirements', 'qualifications', 'benefits']:
                    # Clean and normalize list items
                    cleaned_items = []
                    for item in content:
                        # Remove duplicates and near-duplicates
                        item = TextProcessor.clean_html(item)
                        if item and not any(
                            existing.lower() in item.lower() or item.lower() in existing.lower()
                            for existing in cleaned_items
                        ):
                            cleaned_items.append(item)
                    processed[field] = cleaned_items
                else:
                    processed[field] = content
            else:
                processed[field] = content
                
        return processed 