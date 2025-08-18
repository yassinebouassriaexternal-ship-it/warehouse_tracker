#!/usr/bin/env python3
"""
Wage Rate Database Restructuring Tool

This script cleans up and restructures the wage rates database to follow
proper business rules and eliminate duplicates.

Business Rules:
1. Worker Identification: worker_id corresponds to worker's name
2. Base Rate: $16 for general labor, $18 for forklift driver (can be manually overridden)
3. Markup Rules: Date-based markup per agency
4. No Duplicates: One entry per worker per effective date range
5. Purpose: Calculate monthly expenses accurately

Usage:
    python wage_rate_restructure.py [--dry-run] [--backup]

Options:
    --dry-run    Show what would be changed without making changes
    --backup     Create backup before making changes
"""

import os
import sys
import argparse
from datetime import datetime, date
import pandas as pd

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from app import create_app, db
from app.models import Worker, WageRate, Agency, AgencyMarkup, TimesheetEntry
from app.validation import normalize_position, get_base_rate_for_position


class WageRateRestructurer:
    """Handles wage rate database restructuring and cleanup."""
    
    def __init__(self, app_context):
        self.app = app_context
        self.changes_made = {
            'duplicates_removed': 0,
            'entries_updated': 0,
            'entries_created': 0,
            'workers_processed': 0,
            'errors': []
        }
    
    def analyze_current_state(self):
        """Analyze the current state of wage rates database."""
        print("=== Current Wage Rate Database Analysis ===")
        
        # Get all wage rates
        all_wages = WageRate.query.all()
        total_entries = len(all_wages)
        
        # Group by worker to find duplicates
        worker_entries = {}
        complete_entries = 0
        incomplete_entries = 0
        
        for wage in all_wages:
            if wage.worker_id not in worker_entries:
                worker_entries[wage.worker_id] = []
            worker_entries[wage.worker_id].append(wage)
            
            # Check completeness
            if (wage.role and wage.base_rate is not None and 
                wage.markup is not None and wage.effective_date):
                complete_entries += 1
            else:
                incomplete_entries += 1
        
        duplicate_workers = {k: v for k, v in worker_entries.items() if len(v) > 1}
        
        print(f"Total wage rate entries: {total_entries}")
        print(f"Unique workers: {len(worker_entries)}")
        print(f"Workers with duplicates: {len(duplicate_workers)}")
        print(f"Complete entries: {complete_entries}")
        print(f"Incomplete entries: {incomplete_entries}")
        
        return {
            'total_entries': total_entries,
            'unique_workers': len(worker_entries),
            'duplicate_workers': duplicate_workers,
            'complete_entries': complete_entries,
            'incomplete_entries': incomplete_entries
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
    
    def determine_worker_position(self, worker_id):
        """Determine worker position from timesheet data."""
        # First check existing wage rate
        existing_wage = WageRate.query.filter(
            WageRate.worker_id == worker_id,
            WageRate.role.isnot(None)
        ).first()
        
        if existing_wage and existing_wage.role:
            return existing_wage.role
        
        # If no role in wage rates, check timesheet data for position info
        # This would require position data in timesheet entries
        # For now, default to general labor
        return 'general labor'
    
    def determine_worker_agency(self, worker_id):
        """Determine worker's current agency (most recent) from timesheet data."""
        return self.get_worker_current_agency(worker_id)
    
    def get_worker_hire_date(self, worker_id):
        """Get worker's hire date from first timesheet entry."""
        first_entry = TimesheetEntry.query.filter_by(
            worker_id=worker_id
        ).order_by(TimesheetEntry.date.asc()).first()
        
        return first_entry.date if first_entry else date.today()
    
    def get_worker_current_agency(self, worker_id):
        """Get worker's most recent agency from timesheet data (for agency transfers)."""
        # Get the most recent timesheet entry for this worker
        recent_entry = TimesheetEntry.query.filter(
            TimesheetEntry.worker_id == worker_id,
            TimesheetEntry.agency.isnot(None)
        ).order_by(TimesheetEntry.date.desc()).first()
        
        if recent_entry:
            return recent_entry.agency
        
        # Fallback to existing wage rate agency
        existing_wage = WageRate.query.filter(
            WageRate.worker_id == worker_id,
            WageRate.agency.isnot(None)
        ).first()
        
        return existing_wage.agency if existing_wage else None
    
    def calculate_correct_wage_rate(self, worker_id, position=None, agency=None, effective_date=None, base_rate_override=None, use_current_agency=True):
        """
        Calculate the correct wage rate for a worker following business rules.
        
        Business Rules:
        1. Effective date = worker's first appearance (hire date)
        2. Agency = worker's most recent agency (for transfers)
        3. Base rate can be manually overridden (for pay raises)
        """
        
        # Determine position if not provided
        if not position:
            position = self.determine_worker_position(worker_id)
        
        # Determine agency - use current agency for transfers
        if not agency:
            if use_current_agency:
                agency = self.get_worker_current_agency(worker_id)
            else:
                agency = self.determine_worker_agency(worker_id)
            
            if not agency:
                raise ValueError(f"Cannot determine agency for worker {worker_id}")
        
        # BUSINESS RULE: Effective date is ALWAYS the worker's first appearance (hire date)
        hire_date = self.get_worker_hire_date(worker_id)
        if not effective_date:
            effective_date = hire_date
        
        # Calculate base rate (with override support)
        if base_rate_override is not None:
            base_rate = base_rate_override
        else:
            normalized_position = normalize_position(position)
            base_rate = get_base_rate_for_position(normalized_position)
        
        # Get agency markup for the current agency (not historical)
        # Use today's date for markup calculation to get current rates
        markup = self.get_agency_markup_for_date(agency, date.today())
        
        return {
            'base_rate': base_rate,
            'role': normalize_position(position),
            'agency': agency,
            'markup': markup,
            'effective_date': hire_date,  # Always use hire date
            'hire_date': hire_date,
            'current_agency': agency
        }
    
    def select_best_wage_entry(self, wage_entries):
        """Select the best wage entry from duplicates."""
        if len(wage_entries) == 1:
            return wage_entries[0]
        
        # Scoring system to find the best entry
        scored_entries = []
        
        for entry in wage_entries:
            score = 0
            
            # Prefer entries with complete data
            if entry.role:
                score += 10
            if entry.base_rate is not None:
                score += 10
            if entry.markup is not None:
                score += 10
            if entry.effective_date:
                score += 10
            
            # Prefer more recent effective dates
            if entry.effective_date:
                days_diff = (date.today() - entry.effective_date).days
                score += max(0, 365 - days_diff) / 365 * 5  # Up to 5 points for recency
            
            scored_entries.append((score, entry))
        
        # Sort by score (highest first)
        scored_entries.sort(key=lambda x: x[0], reverse=True)
        
        return scored_entries[0][1]  # Return entry with highest score
    
    def clean_duplicate_entries(self, dry_run=False):
        """Clean up duplicate wage rate entries."""
        print("\n=== Cleaning Duplicate Entries ===")
        
        # Get all workers with multiple entries
        worker_entries = {}
        for wage in WageRate.query.all():
            if wage.worker_id not in worker_entries:
                worker_entries[wage.worker_id] = []
            worker_entries[wage.worker_id].append(wage)
        
        duplicate_workers = {k: v for k, v in worker_entries.items() if len(v) > 1}
        
        print(f"Found {len(duplicate_workers)} workers with duplicate entries")
        
        for worker_id, entries in duplicate_workers.items():
            try:
                print(f"\nProcessing {worker_id} ({len(entries)} entries):")
                
                # Show current entries
                for i, entry in enumerate(entries, 1):
                    print(f"  Entry {i}: Role={entry.role}, Base=${entry.base_rate or 'None'}, "
                          f"Markup={entry.markup or 'None'}, Date={entry.effective_date}")
                
                # Select the best entry to keep
                best_entry = self.select_best_wage_entry(entries)
                entries_to_remove = [e for e in entries if e.id != best_entry.id]
                
                print(f"  → Keeping entry with ID {best_entry.id}")
                print(f"  → Removing {len(entries_to_remove)} duplicate entries")
                
                if not dry_run:
                    # Remove duplicate entries
                    for entry in entries_to_remove:
                        db.session.delete(entry)
                    
                    self.changes_made['duplicates_removed'] += len(entries_to_remove)
                
            except Exception as e:
                error_msg = f"Error processing duplicates for {worker_id}: {str(e)}"
                print(f"  ERROR: {error_msg}")
                self.changes_made['errors'].append(error_msg)
        
        if not dry_run:
            db.session.flush()  # Don't commit yet, just flush
    
    def update_wage_rates_with_business_rules(self, dry_run=False):
        """Update all wage rates to follow proper business rules."""
        print("\n=== Updating Wage Rates with Business Rules ===")
        
        # Get all remaining wage rates after cleanup
        all_wages = WageRate.query.all()
        
        for wage in all_wages:
            try:
                worker_id = wage.worker_id
                print(f"\nProcessing {worker_id}:")
                
                # Check if entry needs updating
                needs_update = False
                update_reasons = []
                
                # Get worker's current agency (for agency transfer detection)
                current_agency = self.get_worker_current_agency(worker_id)
                hire_date = self.get_worker_hire_date(worker_id)
                
                # Check for missing data
                if not wage.role:
                    needs_update = True
                    update_reasons.append("missing role")
                
                if wage.base_rate is None:
                    needs_update = True
                    update_reasons.append("missing base rate")
                
                if wage.markup is None:
                    needs_update = True
                    update_reasons.append("missing markup")
                
                if not wage.effective_date:
                    needs_update = True
                    update_reasons.append("missing effective date")
                
                # Check for agency transfer
                if wage.agency != current_agency:
                    needs_update = True
                    update_reasons.append(f"agency transfer ({wage.agency} → {current_agency})")
                
                # Check if effective date is wrong (should be hire date)
                if wage.effective_date and wage.effective_date != hire_date:
                    needs_update = True
                    update_reasons.append(f"wrong effective date ({wage.effective_date} → {hire_date})")
                
                # Calculate correct values using current agency
                try:
                    # Detect if there's a manual base rate override
                    has_manual_override = False
                    base_rate_override = None
                    
                    if wage.base_rate is not None and wage.role:
                        standard_rate = get_base_rate_for_position(wage.role)
                        if abs(wage.base_rate - standard_rate) > 0.01:
                            has_manual_override = True
                            base_rate_override = wage.base_rate
                            print(f"  → Detected manual override: ${wage.base_rate} (standard: ${standard_rate})")
                    
                    correct_values = self.calculate_correct_wage_rate(
                        worker_id=worker_id,
                        position=wage.role,
                        agency=current_agency,  # Use current agency
                        base_rate_override=base_rate_override if has_manual_override else None
                    )
                    
                    # Check if values are incorrect
                    if wage.role and wage.role != correct_values['role']:
                        needs_update = True
                        update_reasons.append(f"role mismatch ({wage.role} → {correct_values['role']})")
                    
                    # Only update base rate if no manual override
                    if (wage.base_rate is not None and not has_manual_override and
                        abs(wage.base_rate - correct_values['base_rate']) > 0.01):
                        needs_update = True
                        update_reasons.append(f"base rate incorrect (${wage.base_rate} → ${correct_values['base_rate']})")
                    
                    if (wage.markup is not None and 
                        abs(wage.markup - correct_values['markup']) > 0.001):
                        needs_update = True
                        update_reasons.append(f"markup incorrect ({wage.markup:.1%} → {correct_values['markup']:.1%})")
                
                except Exception as e:
                    error_msg = f"Could not calculate correct values for {worker_id}: {str(e)}"
                    print(f"  ERROR: {error_msg}")
                    self.changes_made['errors'].append(error_msg)
                    continue
                
                if needs_update:
                    print(f"  → Needs update: {', '.join(update_reasons)}")
                    
                    if not dry_run:
                        # Update the wage entry
                        if not wage.role:
                            wage.role = correct_values['role']
                        
                        # Only update base rate if no manual override
                        if wage.base_rate is None or not has_manual_override:
                            wage.base_rate = correct_values['base_rate']
                        
                        if wage.markup is None or wage.agency != current_agency:
                            wage.markup = correct_values['markup']
                        
                        # Always update agency to current agency
                        wage.agency = current_agency
                        
                        # Always set effective date to hire date
                        wage.effective_date = hire_date
                        
                        self.changes_made['entries_updated'] += 1
                else:
                    print(f"  → No update needed")
                
                self.changes_made['workers_processed'] += 1
                
            except Exception as e:
                error_msg = f"Error updating wage rate for {wage.worker_id}: {str(e)}"
                print(f"  ERROR: {error_msg}")
                self.changes_made['errors'].append(error_msg)
    
    def create_backup(self):
        """Create backup of current wage rates."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"backup_wage_rates_{timestamp}.csv"
        
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
    
    def restructure(self, dry_run=False, create_backup=False):
        """Main restructuring process."""
        print("Wage Rate Database Restructuring")
        print("=" * 50)
        
        if dry_run:
            print("DRY RUN MODE - No changes will be made")
        
        # Create backup if requested
        if create_backup and not dry_run:
            self.create_backup()
        
        # Analyze current state
        analysis = self.analyze_current_state()
        
        # Clean duplicate entries
        self.clean_duplicate_entries(dry_run)
        
        # Update wage rates with business rules
        self.update_wage_rates_with_business_rules(dry_run)
        
        # Show summary
        print("\n" + "=" * 50)
        print("=== RESTRUCTURING SUMMARY ===")
        print(f"Workers processed: {self.changes_made['workers_processed']}")
        print(f"Duplicate entries removed: {self.changes_made['duplicates_removed']}")
        print(f"Entries updated: {self.changes_made['entries_updated']}")
        print(f"Entries created: {self.changes_made['entries_created']}")
        
        if self.changes_made['errors']:
            print(f"\nErrors encountered: {len(self.changes_made['errors'])}")
            for error in self.changes_made['errors'][:5]:  # Show first 5 errors
                print(f"  - {error}")
            if len(self.changes_made['errors']) > 5:
                print(f"  ... and {len(self.changes_made['errors']) - 5} more errors")
        
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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true', 
                        help='Show what would be changed without making changes')
    parser.add_argument('--backup', action='store_true',
                        help='Create backup before making changes')
    args = parser.parse_args()
    
    app = create_app()
    with app.app_context():
        restructurer = WageRateRestructurer(app)
        success = restructurer.restructure(
            dry_run=args.dry_run,
            create_backup=args.backup
        )
        
        if not success:
            sys.exit(1)


if __name__ == "__main__":
    main()