import os
import json
import logging
from typing import Dict, List, Optional
import requests
from datetime import datetime

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-7b03fa27df1a43e897933f676374933b")

class LLMProcessor:
    def __init__(self):
        self.api_key = DEEPSEEK_API_KEY
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _call_llm(self, messages: List[Dict]) -> Optional[str]:
        """Make an API call to Deepseek."""
        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json={
                    "model": "deepseek-chat",
                    "messages": messages,
                    "temperature": 0.1  # Low temperature for consistent outputs
                }
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logging.error(f"LLM API call failed: {str(e)}")
            return None

    def process_job_details(self, raw_job_data: Dict) -> Dict:
        """Process job details using LLM to properly categorize and structure information."""
        
        # Construct the prompt
        system_prompt = """You are an expert job data processor. Your task is to analyze job posting data and structure it into clear, well-defined categories. Focus on accuracy and proper categorization of information.

For each field, follow these specific guidelines:
- title: Clean, professional job title in title case
- company: Company name in proper case
- location: Standardized location format (City, State, Country) and/or Remote status
- description: Clear, concise summary of the role
- requirements: List of MUST-HAVE skills and qualifications
- qualifications: List of NICE-TO-HAVE skills and preferred qualifications
- benefits: List of company benefits and perks
- employment_type: full-time, part-time, contract, internship
- experience_level: entry-level, junior, mid-level, senior, principal
- work_types: List containing any of: remote, hybrid, on-site
- salary_min: Minimum salary as integer (if provided)
- salary_max: Maximum salary as integer (if provided)
- salary_type: hourly, yearly, or null
- salary_currency: USD, EUR, etc. or null

Return the processed data in valid JSON format."""

        # Convert raw job data to a string representation
        job_data_str = json.dumps(raw_job_data, indent=2)

        user_prompt = f"""Please process this job posting data and return a properly structured JSON object:

{job_data_str}

Focus on:
1. Correctly categorizing requirements vs qualifications
2. Standardizing location format
3. Extracting accurate salary information
4. Determining correct experience level
5. Identifying work type (remote/hybrid/onsite)
6. Cleaning and standardizing all fields

Return only the JSON object with no additional text."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            # Get LLM response
            llm_response = self._call_llm(messages)
            if not llm_response:
                return raw_job_data

            # Parse the JSON response
            processed_data = json.loads(llm_response)

            # Ensure all required fields are present
            required_fields = {
                "title", "company", "location", "description", 
                "requirements", "qualifications", "benefits",
                "employment_type", "experience_level", "work_types"
            }
            
            for field in required_fields:
                if field not in processed_data:
                    processed_data[field] = raw_job_data.get(field)

            # Ensure arrays are properly formatted
            list_fields = ["requirements", "qualifications", "benefits", "work_types"]
            for field in list_fields:
                if not isinstance(processed_data.get(field), list):
                    processed_data[field] = []

            # Add metadata fields
            processed_data.update({
                "source": raw_job_data.get("source"),
                "application_url": raw_job_data.get("application_url"),
                "company_logo": raw_job_data.get("company_logo"),
                "posted_date": raw_job_data.get("posted_date", datetime.now().isoformat()),
                "expires_at": raw_job_data.get("expires_at"),
                "scraped_at": datetime.now().isoformat(),
                "status": "active",
                "job_hash": raw_job_data.get("job_hash")
            })

            return processed_data

        except Exception as e:
            logging.error(f"Error processing job details with LLM: {str(e)}")
            return raw_job_data

    def extract_experience_level(self, title: str, description: str) -> str:
        """Use LLM to determine experience level from job title and description."""
        prompt = f"""Determine the experience level for this job based on the title and description.
Return only one of: entry-level, junior, mid-level, senior, principal

Title: {title}

Description: {description}

Return only the experience level, nothing else."""

        messages = [
            {"role": "system", "content": "You are an expert at determining job experience levels."},
            {"role": "user", "content": prompt}
        ]

        response = self._call_llm(messages)
        if response:
            response = response.strip().lower()
            valid_levels = {"entry-level", "junior", "mid-level", "senior", "principal"}
            if response in valid_levels:
                return response

        return "mid-level"  # Default if unable to determine

    def clean_requirements(self, requirements: List[str]) -> List[str]:
        """Use LLM to clean and standardize requirements."""
        if not requirements:
            return []

        prompt = f"""Clean and standardize these job requirements. Remove duplicates and near-duplicates.
Format each requirement as a clear, concise statement.

Requirements:
{json.dumps(requirements, indent=2)}

Return the cleaned requirements as a JSON array with no additional text."""

        messages = [
            {"role": "system", "content": "You are an expert at cleaning and standardizing job requirements."},
            {"role": "user", "content": prompt}
        ]

        response = self._call_llm(messages)
        if response:
            try:
                cleaned = json.loads(response)
                if isinstance(cleaned, list):
                    return cleaned
            except:
                pass

        return requirements  # Return original if processing fails 