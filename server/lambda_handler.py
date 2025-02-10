import json
import logging
from config.queries import COMPREHENSIVE_JOB_QUERY
from utils.database import SupabaseClient
from utils.engine import (
    TBS,
    JobSite,
    find_jobs,
    handle_job_insert,
)
import boto3
from botocore.exceptions import ClientError

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_secret():
    """Get Supabase credentials from AWS Secrets Manager"""
    secret_name = "prod/jobscraper/supabase"
    region_name = "us-east-1"  # Change to your region
    
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        logger.error(f"Failed to get secret: {str(e)}")
        raise e
    else:
        if 'SecretString' in get_secret_value_response:
            secret = json.loads(get_secret_value_response['SecretString'])
            return secret['SUPABASE_URL'], secret['SUPABASE_KEY']

def lambda_handler(event, context):
    """AWS Lambda handler for the job scraper"""
    try:
        # Get Supabase credentials from Secrets Manager
        supabase_url, supabase_key = get_secret()
        
        # Set up environment with secrets
        import os
        os.environ['SUPABASE_URL'] = supabase_url
        os.environ['SUPABASE_KEY'] = supabase_key
        
        # Run the job scraper
        job_urls_by_board = find_jobs(
            COMPREHENSIVE_JOB_QUERY,
            [JobSite.LEVER, JobSite.GREENHOUSE, JobSite.ASHBY],
            TBS.PAST_TWELVE_HOURS,
            200,
        )
        
        # Initialize Supabase client and process jobs
        supabase_client = SupabaseClient()
        for job_board, job_urls in job_urls_by_board.items():
            handle_job_insert(supabase_client, job_urls, job_board)
        
        # Prune old jobs
        supabase_client.prune_jobs()
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Job scraping completed successfully',
                'jobs_found': sum(len(urls) for urls in job_urls_by_board.values())
            })
        }
        
    except Exception as e:
        logger.error(f"Error in job scraper: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        } 