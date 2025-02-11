import os
import json
import logging
from typing import Dict, List, Optional
import requests
from datetime import datetime
from utils.llm_text_processor import LLMTextProcessor

class LLMProcessor:
    def __init__(self):
        self.api_key = os.getenv('DEEPSEEK_API_KEY')
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable not set")
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        self.model = "deepseek-chat"
        self.text_processor = LLMTextProcessor()

    def _call_api(self, messages: List[Dict[str, str]], temperature: float = 0.3) -> Optional[str]:
        """Call DeepSeek API with retry logic."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }
        
        try:
            response = requests.post(self.api_url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content']
        except Exception as e:
            logging.error(f"API call failed: {str(e)}")
            return None

    def process_job_details(self, job_details: Dict) -> Optional[Dict]:
        """Process job details using DeepSeek API."""
        # Note: We assume job_details['description'] is already cleaned by TextProcessor
        # in the scraping phase, so no need to clean HTML here
        prompt = self._create_job_enhancement_prompt(job_details)
        
        messages = [
            {"role": "system", "content": "You are an expert job analyst. Your task is to analyze job postings and extract key information in a structured format."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self._call_api(messages)
            if response:
                return self._parse_llm_response(response)
        except Exception as e:
            logging.error(f"Failed to process job details: {str(e)}")
        
        return None

    def _create_job_enhancement_prompt(self, job_details: Dict) -> str:
        """Create a prompt for job enhancement."""
        return f"""Please analyze this job posting and provide a structured response with the following information:

Job Details:
Title: {job_details.get('title', '')}
Company: {job_details.get('company', '')}
Description: {job_details.get('description', '')}
Location: {job_details.get('location', '')}
Requirements: {job_details.get('requirements', [])}
Benefits: {job_details.get('benefits', [])}

Please provide a JSON response with the following fields:
- standardized_title: A clean, standardized version of the job title
- job_category: The general category this job falls under (e.g., Software Development, Data Science, DevOps)
- industry: The primary industry this role is in
- key_skills: A list of key technical and soft skills required (extracted from requirements and description)
- education_level: The minimum required education level
- experience_level: The experience level (entry-level, mid-level, senior, principal)
- work_types: List of work types (remote, hybrid, on-site)
- enhanced_description: A clear, well-structured description of the role
- standardized_benefits: A cleaned list of benefits offered

Format your response as a valid JSON object."""

    def _parse_llm_response(self, response: str) -> Optional[Dict]:
        """Parse the LLM response into a structured format."""
        try:
            # Find JSON content within the response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_content = response[json_start:json_end]
                return json.loads(json_content)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse LLM response: {str(e)}")
        return None

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

        response = self._call_api(messages)
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

        response = self._call_api(messages)
        if response:
            try:
                cleaned = json.loads(response)
                if isinstance(cleaned, list):
                    return cleaned
            except:
                pass

        return requirements  # Return original if processing fails 