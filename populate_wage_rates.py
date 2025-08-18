#!/usr/bin/env python3
"""
Populate missing wage rates for workers in the database.

This script analyzes the current timesheet data and ensures all workers
have appropriate wage rates based on their position and staffing agency.

Usage:
    python populate_wage_rates.py [--dry-run]

Options:
    --dry-run    Show what would be changed without making actual changes
"""

import os
import sys
import argparse
from datetime import date

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from app import create_app, db
from app.models import Worker, WageRate, Agency, AgencyMarkup, TimesheetEntry
from app.utils import update_all_worker_wage_rates, populate_missing_wage_rates
import pandas as pd


def load_timesheet_data():
    """Load all timesheet data from the database."""
    app = create_app()
    with app.app_context():
        # Query all timesheet entries with position info from wage rates
        query = db.session.query(
            TimesheetEntry.worker_id,
            TimesheetEntry.date,
            TimesheetEntry.agency,
            WageRate.role.label('position')
        ).outerjoin(
            WageRate, TimesheetEntry.worker_id == WageRate.worker_id
        ).all()
        
        if not query:
            print("No timesheet data found in database.")
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(query, columns=['worker_id', 'date', 'agency', 'position'])
        
        # Fill missing positions with 'general labor' as default
        df['position'] = df['position'].fillna('general labor')
        
        return df


def analyze_current_state():
    """Analyze the current state of wage rates in the database."""
    app = create_app()
    with app.app_context():
        # Get worker counts
        total_workers = Worker.query.count()
        workers_with_wage_rates = db.session.query(Worker.worker_id).join(
            WageRate, Worker.worker_id == WageRate.worker_id
        ).distinct().count()
        workers_without_wage_rates = total_workers - workers_with_wage_rates
        
        # Get timesheet workers
        timesheet_workers = db.session.query(TimesheetEntry.worker_id).distinct().count()
        
        # Get agency info
        agencies = Agency.query.count()
        agency_markups = AgencyMarkup.query.count()
        
        print("=== Current Database State ===")
        print(f"Total workers: {total_workers}")
        print(f"Workers with wage rates: {workers_with_wage_rates}")
        print(f"Workers without wage rates: {workers_without_wage_rates}")
        print(f"Workers in timesheet data: {timesheet_workers}")
        print(f"Agencies: {agencies}")
        print(f"Agency markup records: {agency_markups}")
        print()
        
        return {
            'total_workers': total_workers,
            'workers_with_wage_rates': workers_with_wage_rates,
            'workers_without_wage_rates': workers_without_wage_rates,
            'timesheet_workers': timesheet_workers
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true', 
                        help='Show what would be changed without making actual changes')
    args = parser.parse_args()
    
    print("Warehouse Tracker - Wage Rate Population Tool")
    print("=" * 50)
    
    # Analyze current state
    state = analyze_current_state()
    
    if state['timesheet_workers'] == 0:
        print("No timesheet data found. Nothing to process.")
        return
    
    # Load timesheet data
    print("Loading timesheet data...")
    df = load_timesheet_data()
    
    if df is None or df.empty:
        print("Failed to load timesheet data.")
        return
    
    print(f"Loaded {len(df)} timesheet entries for {df['worker_id'].nunique()} unique workers.")
    
    # Create app context and populate wage rates
    app = create_app()
    with app.app_context():
        # Set the timesheet data in app config for the utility functions
        app.config['MASTER_TIMESHEET_DF'] = df
        
        print("\nProcessing wage rates...")
        if args.dry_run:
            print("DRY RUN MODE - No changes will be made")
        
        summary = update_all_worker_wage_rates(dry_run=args.dry_run)
        
        print("\n=== Processing Summary ===")
        if 'error' in summary:
            print(f"Error: {summary['error']}")
        else:
            print(f"Workers processed: {summary.get('workers_processed', 0)}")
            print(f"Wage rates created: {summary.get('wage_rates_created', 0)}")
            print(f"Wage rates updated: {summary.get('wage_rates_updated', 0)}")
            
            if summary.get('errors'):
                print(f"\nErrors encountered:")
                for error in summary['errors']:
                    print(f"  - {error}")
        
        if not args.dry_run and not summary.get('error'):
            print("\nWage rate population completed successfully!")
        elif args.dry_run:
            print("\nDry run completed. Use without --dry-run to apply changes.")


if __name__ == "__main__":
    main()