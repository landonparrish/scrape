from flask import Flask, request, Response
import logging
from config.queries import COMPREHENSIVE_JOB_QUERY
from utils.database import SupabaseClient
from utils.engine import (
    TBS,
    JobSite,
    find_jobs,
    handle_job_insert,
)
from utils.validator import new_validator
import os
from dotenv import load_dotenv
from http import HTTPStatus
from datetime import datetime
from typing import Dict, List, Optional
from utils.text_processor import TextProcessor
from scrapers.lever import LeverScraper
from scrapers.greenhouse import GreenhouseScraper
from scrapers.ashby import AshbyScraper
from scrapers.wellfound import WellfoundScraper

load_dotenv()

MERGENT_API_KEY = os.getenv("MERGENT_API_KEY")


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = Flask(__name__)


@app.route("/api/mergent/tasks", methods=["POST"])
def mergent_task_handler():
    try:
        validator = new_validator(MERGENT_API_KEY)
        validated, response = validator(request)
        validated = True
        if not validated:
            logging.error(f"Failed to validate request: {response.response}")
            return response

        perform_task(request.data.decode())
    except Exception as e:
        error_message = f"Failed to perform task: {str(e)}"
        logging.error(error_message)
        return Response(error_message, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    return Response(status=HTTPStatus.OK)


def perform_task(body):
    job_urls_by_board = find_jobs(
        COMPREHENSIVE_JOB_QUERY,
        [JobSite.LEVER, JobSite.GREENHOUSE, JobSite.ASHBY, JobSite.WELLFOUND],
        TBS.PAST_TWELVE_HOURS,
        200,
    )
    try:
        supabase_client = SupabaseClient()
        for job_board, job_urls in job_urls_by_board.items():
            handle_job_insert(supabase_client, job_urls, job_board)
        supabase_client.prune_jobs()
    except Exception as e:
        logging.error(f"Failed: {str(e)}")


class JobScraper:
    def __init__(self):
        self.db = SupabaseClient()
        self.text_processor = TextProcessor()
        
        # Initialize scrapers
        self.scrapers = {
            'lever': LeverScraper(),
            'greenhouse': GreenhouseScraper(),
            'ashby': AshbyScraper(),
            'wellfound': WellfoundScraper()
        }
        
        # Job sites to scrape
        self.job_sites = [
            # Lever job boards
            {'type': 'lever', 'company': 'Netflix', 'url': 'https://jobs.lever.co/netflix'},
            {'type': 'lever', 'company': 'Figma', 'url': 'https://jobs.lever.co/figma'},
            {'type': 'lever', 'company': 'Databricks', 'url': 'https://jobs.lever.co/databricks'},
            {'type': 'lever', 'company': 'Notion', 'url': 'https://jobs.lever.co/notion'},
            {'type': 'lever', 'company': 'Scale AI', 'url': 'https://jobs.lever.co/scale'},
            
            # Greenhouse job boards
            {'type': 'greenhouse', 'company': 'Discord', 'url': 'https://discord.com/jobs'},
            {'type': 'greenhouse', 'company': 'Stripe', 'url': 'https://stripe.com/jobs'},
            {'type': 'greenhouse', 'company': 'Coinbase', 'url': 'https://www.coinbase.com/careers'},
            {'type': 'greenhouse', 'company': 'Ramp', 'url': 'https://ramp.com/careers'},
            {'type': 'greenhouse', 'company': 'Airtable', 'url': 'https://airtable.com/careers'},
            
            # Ashby job boards
            {'type': 'ashby', 'company': 'Linear', 'url': 'https://linear.app/careers'},
            {'type': 'ashby', 'company': 'Vercel', 'url': 'https://vercel.com/careers'},
            {'type': 'ashby', 'company': 'Retool', 'url': 'https://retool.com/careers'},
            
            # Wellfound job boards
            {'type': 'wellfound', 'company': 'Wellfound', 'url': 'https://wellfound.com/jobs'}
        ]

    def handle_job_insert(self, job_data: Dict) -> Optional[str]:
        """Handle job data insertion with basic HTML cleaning."""
        try:
            # Clean HTML content
            if job_data.get('description'):
                job_data['description'] = self.text_processor.clean_html(job_data['description'])
            
            # Clean location
            if job_data.get('location'):
                job_data['location'] = self.text_processor.clean_location(job_data['location'])
            
            # Extract bullet points from description if needed
            if job_data.get('description') and not job_data.get('requirements'):
                job_data['requirements'] = self.text_processor.extract_bullet_points(job_data['description'])
            
            # Add metadata
            job_data.update({
                'scraped_at': datetime.now().isoformat(),
                'status': 'active',
                'llm_processed': False
            })
            
            # Insert into database
            job_hash = self.db.insert_job(job_data)
            logger.info(f"Successfully inserted job: {job_data.get('title')} at {job_data.get('company')}")
            return job_hash
            
        except Exception as e:
            logger.error(f"Error inserting job: {str(e)}")
            return None

    def scrape_jobs(self) -> Dict[str, int]:
        """Scrape jobs from configured job boards."""
        stats = {
            'total_jobs': 0,
            'processed_jobs': 0,
            'failed_jobs': 0,
            'errors': []
        }
        
        for site in self.job_sites:
            try:
                scraper = self.scrapers.get(site['type'])
                if not scraper:
                    logger.error(f"No scraper found for type: {site['type']}")
                    continue
                
                # Get jobs for this site
                jobs = scraper.scrape_jobs(site['url'], site['company'])
                stats['total_jobs'] += len(jobs)
                
                # Process each job
                for job in jobs:
                    try:
                        if self.handle_job_insert(job):
                            stats['processed_jobs'] += 1
                        else:
                            stats['failed_jobs'] += 1
                    except Exception as e:
                        stats['failed_jobs'] += 1
                        error_msg = f"Error processing job for {site['company']}: {str(e)}"
                        logger.error(error_msg)
                        stats['errors'].append(error_msg)
                        
            except Exception as e:
                error_msg = f"Error scraping {site['company']}: {str(e)}"
                logger.error(error_msg)
                stats['errors'].append(error_msg)
                
        return stats

def main():
    """Main function to run the job scraper."""
    try:
        scraper = JobScraper()
        stats = scraper.scrape_jobs()
        
        logger.info("Job scraping completed!")
        logger.info(f"Total jobs found: {stats['total_jobs']}")
        logger.info(f"Successfully processed: {stats['processed_jobs']}")
        logger.info(f"Failed to process: {stats['failed_jobs']}")
        
        if stats['errors']:
            logger.info("\nErrors encountered:")
            for error in stats['errors']:
                logger.error(error)
                
    except Exception as e:
        logger.error(f"Fatal error in main: {str(e)}")

if __name__ == "__main__":
    main()
