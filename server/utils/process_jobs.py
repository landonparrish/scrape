# server/process_jobs.py
import os
import logging
from datetime import datetime
from typing import Dict, List
from utils.database import SupabaseClient
from utils.llm_processor import LLMProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JobProcessor:
    def __init__(self):
        self.db = SupabaseClient()
        self.llm = LLMProcessor()
        
    def process_pending_jobs(self, batch_size: int = 50) -> Dict[str, int]:
        """Process jobs that haven't been enhanced by LLM."""
        stats = {
            'total_jobs': 0,
            'processed_jobs': 0,
            'failed_jobs': 0,
            'errors': []
        }
        
        try:
            # Get unprocessed jobs
            jobs = self.db.get_unprocessed_jobs(limit=batch_size)
            stats['total_jobs'] = len(jobs)
            
            for job in jobs:
                try:
                    # Process job with LLM
                    enhanced_data = self.llm.process_job_details(job)
                    
                    if enhanced_data:
                        # Add metadata
                        enhanced_data.update({
                            'llm_processed': True,
                            'llm_processed_at': datetime.now().isoformat(),
                            'model_version': 'deepseek-chat'
                        })
                        
                        # Update job in database
                        if self.db.update_job_with_enhancements(job['job_hash'], enhanced_data):
                            stats['processed_jobs'] += 1
                            logger.info(f"Successfully processed job: {job.get('title')} at {job.get('company')}")
                        else:
                            stats['failed_jobs'] += 1
                            error_msg = f"Failed to update job in database: {job.get('job_hash')}"
                            logger.error(error_msg)
                            stats['errors'].append(error_msg)
                    else:
                        stats['failed_jobs'] += 1
                        error_msg = f"LLM processing failed for job: {job.get('job_hash')}"
                        logger.error(error_msg)
                        stats['errors'].append(error_msg)
                        
                except Exception as e:
                    stats['failed_jobs'] += 1
                    error_msg = f"Error processing job {job.get('job_hash')}: {str(e)}"
                    logger.error(error_msg)
                    stats['errors'].append(error_msg)
                    
        except Exception as e:
            error_msg = f"Error getting unprocessed jobs: {str(e)}"
            logger.error(error_msg)
            stats['errors'].append(error_msg)
            
        return stats

def main():
    """Main function to run the job processor."""
    try:
        processor = JobProcessor()
        stats = processor.process_pending_jobs()
        
        logger.info("Job processing completed!")
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