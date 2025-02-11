import re
from bs4 import BeautifulSoup
from typing import List

class TextProcessor:
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
    def identify_section(title: str) -> str:
        """Identify section type from title."""
        title_lower = title.lower()
        
        if any(word in title_lower for word in ["requirement", "qualification", "what you'll need", "what we're looking for"]):
            return "requirements"
        elif any(word in title_lower for word in ["benefit", "perks", "what we offer", "compensation"]):
            return "benefits"
        else:
            return "other"

    @staticmethod
    def clean_location(location: str) -> str:
        """Clean and standardize location string."""
        if not location:
            return ""
        
        # Remove extra whitespace
        location = " ".join(location.split())
        
        # Remove common prefixes
        location = re.sub(r'^(location|where)\s*:\s*', '', location, flags=re.IGNORECASE)
        
        return location.strip() 