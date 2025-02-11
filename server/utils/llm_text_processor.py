import re
from bs4 import BeautifulSoup
from typing import List, Dict

class LLMTextProcessor:
    @staticmethod
    def clean_html(html_content: str) -> str:
        """Clean HTML content to plain text."""
        if not html_content:
            return ""
        
        # Convert <br> to newlines
        html_content = html_content.replace("<br>", "\n").replace("<br/>", "\n")
        
        # Parse HTML and get text
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
            
        # Get text and clean up whitespace
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)
        
        return text

    @staticmethod
    def extract_bullet_points(text: str) -> List[str]:
        """Extract bullet points from text."""
        if not text:
            return []
            
        # Split text into lines
        lines = text.split("\n")
        bullet_points = []
        
        for line in lines:
            # Remove common bullet point markers
            line = line.strip()
            line = re.sub(r'^[\s•\-\*\⁃\●\⚬\○\▪\■\□\▫\–\—\+]+', '', line)
            
            # Skip empty lines or very short ones
            if len(line) > 3:
                bullet_points.append(line)
                
        return bullet_points

    @staticmethod
    def process_job_details(job_details: Dict) -> Dict:
        """Process job details with basic text cleaning."""
        processed = {}
        
        # Process text fields
        for field in ['title', 'company', 'location', 'description']:
            if job_details.get(field):
                processed[field] = LLMTextProcessor.clean_html(job_details[field])
            else:
                processed[field] = job_details.get(field)
        
        # Process lists
        for field in ['requirements', 'benefits', 'work_types']:
            if job_details.get(field):
                if isinstance(job_details[field], str):
                    processed[field] = LLMTextProcessor.extract_bullet_points(job_details[field])
                else:
                    processed[field] = job_details[field]
            else:
                processed[field] = job_details.get(field, [])
        
        # Copy other fields as is
        for field in job_details:
            if field not in processed:
                processed[field] = job_details[field]
        
        return processed 