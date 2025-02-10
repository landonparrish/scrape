# Job Scraper

Automated job scraper that collects job postings from various job boards and stores them in a Supabase database.

## Features
- Scrapes jobs from Lever, Greenhouse, and Ashby job boards
- Runs every 6 hours via GitHub Actions
- Stores data in Supabase
- Automatic error reporting
- Secure credential handling

## Setup

1. **Environment Variables**
   Create a `.env` file in the `server` directory with:
   ```
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_key
   ```

2. **Install Dependencies**
   ```bash
   cd server
   poetry install
   ```

3. **GitHub Secrets**
   Add these repository secrets:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`

## Development

1. **Local Testing**
   ```bash
   cd server
   poetry run python test_connection.py
   ```

2. **Manual Trigger**
   - Go to Actions tab
   - Select "Job Scraper"
   - Click "Run workflow"

## Architecture
- Python 3.11
- Poetry for dependency management
- GitHub Actions for scheduling
- Supabase for data storage

## Contributing
1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

