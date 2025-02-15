from datetime import datetime, timedelta
import os
from supabase import create_client
from dotenv import load_dotenv
import logging

load_dotenv()

SUPABASE_URL: str = os.getenv("SUPABASE_URL")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase credentials must be set in environment variables.")


class SupabaseClient:
    def __init__(self):
        self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Force schema refresh on init
        self._refresh_schema()

    def _refresh_schema(self):
        """Force a schema refresh to ensure we have the latest table structure."""
        self.client.postgrest.schema('public')

    def insert_job(self, job):
        """Legacy insert method - prefer upsert_job instead."""
        self._refresh_schema()  # Refresh before insert
        self.client.table("jobs").insert(job).execute()

    def upsert_job(self, job):
        """Insert or update a job based on job_hash."""
        self._refresh_schema()  # Refresh before upsert
        # Upsert based on job_hash, updating all fields if the job exists
        self.client.table("jobs").upsert(
            job,
            on_conflict="job_hash"
        ).execute()

    def get_all_jobs(self):
        self._refresh_schema()  # Refresh before select
        return self.client.table("jobs").select("*").execute()

    def get_last_24hrs_jobs(self):
        self._refresh_schema()  # Refresh before select
        return self.client.table("jobs").select("*").execute()

    def get_last_3_jobs(self):
        self._refresh_schema()  # Refresh before select
        return self.client.table("jobs").select("*").limit(3).execute()

    def prune_jobs(self):
        """Remove old jobs and duplicates."""
        try:
            self._refresh_schema()  # Refresh before operations
            
            # Remove jobs older than 2 months based on scraped_at
            current_time = datetime.now()
            old_jobs_query = self.client.table("jobs").delete().lt(
                "scraped_at", (current_time - timedelta(days=60)).isoformat()
            )
            old_jobs_result = old_jobs_query.execute()
            logging.info(f"Removed {len(old_jobs_result.data) if old_jobs_result.data else 0} old jobs")
            
            # Keep only the most recent version of each job based on job_hash
            dedup_result = self.client.rpc(
                'deduplicate_jobs',
                {}  # No parameters needed
            ).execute()
            logging.info(f"Deduplication complete: {dedup_result.data if dedup_result.data else 'No duplicates found'}")
            
        except Exception as e:
            logging.error(f"Error pruning jobs: {str(e)}", exc_info=True)
            raise
