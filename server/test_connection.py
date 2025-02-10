from utils.database import SupabaseClient
import logging
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta

def test_supabase_connection():
    # Load environment variables
    load_dotenv()
    
    # Verify environment variables are loaded
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_KEY must be set in .env file")
        return False

    try:
        # Initialize Supabase client
        print("Initializing Supabase client...")
        supabase = SupabaseClient()

        # Test connection by trying to fetch jobs
        print("\nTesting connection by fetching jobs...")
        result = supabase.get_all_jobs()
        print(f"Successfully connected! Found {len(result.data)} jobs in the database.")

        # Test insertion with a dummy job matching the exact schema
        test_job = {
            "title": "Test Software Engineer",
            "company": "Test Company",
            "location": "Remote, US",
            "description": "This is a test job posting",
            "salary": "$120,000 - $150,000",
            "remote": True,
            "work_types": "{remote}",  # PostgreSQL text array format
            "employment_type": None,  # Allow null
            "experience_level": "Mid Level",
            "requirements": "{Python,TypeScript}",  # PostgreSQL text array format
            "qualifications": "{\"Bachelor's degree\",\"3+ years experience\"}",  # PostgreSQL text array format
            "benefits": "{\"Health insurance\",\"401k\"}",  # PostgreSQL text array format
            "application_url": "https://test.com/test-job-" + str(hash("test"))[:8],
            "company_logo": "https://test.com/logo.png",
            "posted_date": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "scraped_at": datetime.now().isoformat(),
            "status": "active",
            "salary_min": 120000,
            "salary_max": 150000,
            "salary_currency": "USD",
            "salary_type": "yearly",
            "last_updated": datetime.now().isoformat()
        }

        print("\nTesting job insertion...")
        supabase.insert_job(test_job)
        print("Successfully inserted test job!")

        return True

    except Exception as e:
        print(f"Error testing connection: {str(e)}")
        logging.error(f"Detailed error: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    test_supabase_connection() 