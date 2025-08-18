#!/usr/bin/env python3
"""
Agency Period Wage Rate Management

This script creates proper historical wage rate records:
- One wage rate entry per worker per agency period
- Each entry's effective_date = first appearance under that specific agency
- Maintains complete historical records for accurate cost tracking

Business Rules:
1. Workers who transfer agencies get separate wage rate entries for each agency
2. Effective date = first day worker appeared under that specific agency
3. Each agency period has its own wage rate record
4. Manual base rate overrides are preserved within each period
"""

import os
import sys
from datetime import datetime, date
import pandas as pd

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from app import create_app, db
from app.models import Worker, WageRate, Agency, AgencyMarkup, TimesheetEntry
from app.validation import normalize_position, get_base_rate_for_position


class AgencyPeriodManager:
    """Manages wage rates based on agency periods."""
    
    def __init__(self, app_context):
        self.app = app_context
        self.changes_made = {
            'entries_created': 0,
            'entries_updated': 0,
            'entries_removed': 0,
            'workers_processed': 0,
            'errors': []
        }
    
    def get_agency_markup_for_date(self, agency_name, effective_date):
        """Get agency markup rate for a specific date."""
        if not effective_date:
            effective_date = date.today()
        
        agency = Agency.query.filter_by(name=agency_name).first()
        if not agency:
            return 0.0
        
        markup_obj = AgencyMarkup.query.filter(
            AgencyMarkup.agency_id == agency.id,
            AgencyMarkup.effective_date <= effective_date
        ).order_by(AgencyMarkup.effective_date.desc()).first()
        
        return markup_obj.markup if markup_obj else 0.0
    
    def analyze_worker_agency_periods(self, worker_id):
        """
        Analyze a worker's agency periods from timesheet data.
        Returns a list of agency periods with start dates.
        """
        # Get all timesheet entries for this worker, ordered by date
        timesheet_entries = TimesheetEntry.query.filter_by(
            worker_id=worker_id
        ).order_by(TimesheetEntry.date.asc()).all()
        
        if not timesheet_entries:
            return []
        
        agency_periods = []
        current_agency = None
        period_start = None
        
        for entry in timesheet_entries:
            if entry.agency != current_agency:
                # Agency change detected
                if current_agency is not None:
                    # End previous period (not needed for our purposes, but good to track)
                    pass
                
                # Start new period
                current_agency = entry.agency
                period_start = entry.date
                
                if current_agency:  # Only track periods with actual agencies
                    agency_periods.append({
                        'agency': current_agency,
                        'start_date': period_start,
                        'worker_id': worker_id
                    })
        
        return agency_periods
    
    def determine_worker_position_for_period(self, worker_id, agency, start_date):
        """
        Determine worker position for a specific agency period.
        Uses timesheet data or existing wage rate information.
        """
        # Check existing wage rate for this worker and agency
        existing_wage = WageRate.query.filter_by(
            worker_id=worker_id,
            agency=agency
        ).first()
        
        if existing_wage and existing_wage.role:
            return existing_wage.role
        
        # Default to general labor if no specific info available
        return 'general labor'
    
    def detect_manual_override(self, worker_id, agency, current_base_rate):
        """
        Detect if a worker has a manual base rate override for a specific agency period.
        """
        if current_base_rate is None:
            return False, None
        
        # Get the position for this period
        position = self.determine_worker_position_for_period(worker_id, agency, None)
        standard_rate = get_base_rate_for_position(position)
        
        # If current rate differs from standard by more than 1 cent, it's likely a manual override
        if abs(current_base_rate - standard_rate) > 0.01:
            return True, current_base_rate
        
        return False, None
    
    def create_agency_period_wage_rates(self, dry_run=False):
        """
        Create proper agency period wage rates for all workers.
        """
        print("=== Creating Agency Period Wage Rates ===")
        
        # Get all workers from timesheet data
        workers_with_timesheet = db.session.query(TimesheetEntry.worker_id).distinct().all()
        worker_ids = [w[0] for w in workers_with_timesheet]
        
        print(f"Processing {len(worker_ids)} workers...")
        
        for worker_id in worker_ids:
            try:
                print(f"\nProcessing {worker_id}:")
                
                # Analyze agency periods for this worker
                agency_periods = self.analyze_worker_agency_periods(worker_id)
                
                if not agency_periods:
                    print(f"  → No agency periods found")
                    continue
                
                print(f"  → Found {len(agency_periods)} agency periods:")
                for period in agency_periods:
                    print(f"      {period['agency']} starting {period['start_date']}")
                
                # Get existing wage rates for this worker
                existing_wages = WageRate.query.filter_by(worker_id=worker_id).all()
                existing_agencies = {w.agency: w for w in existing_wages}
                
                # Ensure worker exists in Worker table
                worker = Worker.query.filter_by(worker_id=worker_id).first()
                if not worker:
                    if not dry_run:
                        worker = Worker(worker_id=worker_id, name=None, is_active=True)
                        db.session.add(worker)
                    print(f"  → Would create worker record")
                
                # Process each agency period
                for period in agency_periods:
                    agency = period['agency']
                    start_date = period['start_date']
                    
                    # Check if we already have a wage rate for this agency
                    existing_wage = existing_agencies.get(agency)
                    
                    if existing_wage:
                        # Update existing wage rate
                        needs_update = False
                        update_reasons = []
                        
                        # Check if effective date is correct
                        if existing_wage.effective_date != start_date:
                            needs_update = True
                            update_reasons.append(f"effective date ({existing_wage.effective_date} → {start_date})")
                        
                        # Determine position and rates
                        position = self.determine_worker_position_for_period(worker_id, agency, start_date)
                        
                        # Check for manual override
                        has_override, override_rate = self.detect_manual_override(
                            worker_id, agency, existing_wage.base_rate
                        )
                        
                        if has_override:
                            base_rate = override_rate
                            print(f"      → Preserving manual override: ${base_rate:.2f} for {agency}")
                        else:
                            base_rate = get_base_rate_for_position(position)
                        
                        # Get markup for this agency and date
                        markup = self.get_agency_markup_for_date(agency, start_date)
                        
                        # Check for other changes
                        if not existing_wage.role:
                            needs_update = True
                            update_reasons.append("missing role")
                        
                        if existing_wage.base_rate is None:
                            needs_update = True
                            update_reasons.append("missing base rate")
                        elif not has_override and abs(existing_wage.base_rate - base_rate) > 0.01:
                            needs_update = True
                            update_reasons.append(f"base rate ({existing_wage.base_rate} → {base_rate})")
                        
                        if existing_wage.markup is None or abs(existing_wage.markup - markup) > 0.001:
                            needs_update = True
                            update_reasons.append(f"markup ({existing_wage.markup:.1%} → {markup:.1%})")
                        
                        if needs_update:
                            print(f"      → Updating {agency}: {', '.join(update_reasons)}")
                            
                            if not dry_run:
                                existing_wage.effective_date = start_date
                                existing_wage.role = position
                                existing_wage.markup = markup
                                
                                # Only update base rate if no manual override
                                if not has_override:
                                    existing_wage.base_rate = base_rate
                                
                                self.changes_made['entries_updated'] += 1
                        else:
                            print(f"      → {agency}: No update needed")
                    
                    else:
                        # Create new wage rate for this agency period
                        position = self.determine_worker_position_for_period(worker_id, agency, start_date)
                        base_rate = get_base_rate_for_position(position)
                        markup = self.get_agency_markup_for_date(agency, start_date)
                        
                        print(f"      → Creating new wage rate for {agency}")
                        print(f"          Position: {position}, Base: ${base_rate:.2f}, Markup: {markup:.1%}")
                        
                        if not dry_run:
                            new_wage = WageRate(
                                worker_id=worker_id,
                                base_rate=base_rate,
                                role=position,
                                agency=agency,
                                markup=markup,
                                effective_date=start_date
                            )
                            db.session.add(new_wage)
                            self.changes_made['entries_created'] += 1
                
                # Remove wage rates for agencies the worker no longer works for
                current_agencies = {p['agency'] for p in agency_periods}
                for agency, wage_rate in existing_agencies.items():
                    if agency not in current_agencies:
                        print(f"      → Removing outdated wage rate for {agency}")
                        if not dry_run:
                            db.session.delete(wage_rate)
                            self.changes_made['entries_removed'] += 1
                
                self.changes_made['workers_processed'] += 1
                
            except Exception as e:
                error_msg = f"Error processing worker {worker_id}: {str(e)}"
                print(f"  ERROR: {error_msg}")
                self.changes_made['errors'].append(error_msg)
        
        if not dry_run:
            db.session.flush()
    
    def create_backup(self):
        """Create backup of current wage rates."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"backup_wage_rates_agency_periods_{timestamp}.csv"
        
        # Export current wage rates
        wage_rates = WageRate.query.all()
        data = []
        for wr in wage_rates:
            data.append({
                'id': wr.id,
                'worker_id': wr.worker_id,
                'base_rate': wr.base_rate,
                'role': wr.role,
                'agency': wr.agency,
                'markup': wr.markup,
                'effective_date': wr.effective_date
            })
        
        df = pd.DataFrame(data)
        df.to_csv(backup_file, index=False)
        print(f"Backup created: {backup_file}")
        return backup_file
    
    def analyze_current_state(self):
        """Analyze current state before making changes."""
        print("=== Current Wage Rate Analysis ===")
        
        # Get workers with multiple agencies
        workers_with_transfers = []
        
        workers_with_timesheet = db.session.query(TimesheetEntry.worker_id).distinct().all()
        
        for worker_tuple in workers_with_timesheet:
            worker_id = worker_tuple[0]
            agencies = db.session.query(TimesheetEntry.agency).filter_by(
                worker_id=worker_id
            ).distinct().all()
            
            agency_list = [a[0] for a in agencies if a[0]]
            
            if len(agency_list) > 1:
                workers_with_transfers.append({
                    'worker_id': worker_id,
                    'agencies': agency_list
                })
        
        print(f"Workers with agency transfers: {len(workers_with_transfers)}")
        
        if workers_with_transfers:
            print("\nExamples of workers with agency transfers:")
            for i, worker in enumerate(workers_with_transfers[:10]):
                print(f"  {i+1}. {worker['worker_id']}: {' → '.join(worker['agencies'])}")
        
        # Check current wage rate structure
        current_wages = WageRate.query.all()
        workers_with_multiple_wages = {}
        
        for wage in current_wages:
            if wage.worker_id not in workers_with_multiple_wages:
                workers_with_multiple_wages[wage.worker_id] = []
            workers_with_multiple_wages[wage.worker_id].append(wage)
        
        workers_with_multiple = {k: v for k, v in workers_with_multiple_wages.items() if len(v) > 1}
        
        print(f"\nCurrent workers with multiple wage rates: {len(workers_with_multiple)}")
        
        return {
            'workers_with_transfers': workers_with_transfers,
            'workers_with_multiple_wages': workers_with_multiple
        }
    
    def restructure(self, dry_run=False, create_backup=False):
        """Main restructuring process for agency periods."""
        print("Agency Period Wage Rate Restructuring")
        print("=" * 50)
        
        if dry_run:
            print("DRY RUN MODE - No changes will be made")
        
        # Create backup if requested
        if create_backup and not dry_run:
            self.create_backup()
        
        # Analyze current state
        analysis = self.analyze_current_state()
        
        # Create agency period wage rates
        self.create_agency_period_wage_rates(dry_run)
        
        # Show summary
        print("\n" + "=" * 50)
        print("=== RESTRUCTURING SUMMARY ===")
        print(f"Workers processed: {self.changes_made['workers_processed']}")
        print(f"Wage rate entries created: {self.changes_made['entries_created']}")
        print(f"Wage rate entries updated: {self.changes_made['entries_updated']}")
        print(f"Wage rate entries removed: {self.changes_made['entries_removed']}")
        
        if self.changes_made['errors']:
            print(f"\nErrors encountered: {len(self.changes_made['errors'])}")
            for error in self.changes_made['errors'][:5]:
                print(f"  - {error}")
        
        if not dry_run:
            try:
                db.session.commit()
                print("\n✅ Changes committed to database successfully!")
            except Exception as e:
                db.session.rollback()
                print(f"\n❌ Error committing changes: {e}")
                return False
        else:
            db.session.rollback()
            print("\n🔍 Dry run completed. Use without --dry-run to apply changes.")
        
        return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true', 
                        help='Show what would be changed without making changes')
    parser.add_argument('--backup', action='store_true',
                        help='Create backup before making changes')
    args = parser.parse_args()
    
    app = create_app()
    with app.app_context():
        manager = AgencyPeriodManager(app)
        success = manager.restructure(
            dry_run=args.dry_run,
            create_backup=args.backup
        )
        
        if not success:
            sys.exit(1)


if __name__ == "__main__":
    main()