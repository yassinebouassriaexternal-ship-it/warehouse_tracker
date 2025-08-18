#!/usr/bin/env python3
"""
Test the updated business rules for wage rates.

This script analyzes the current database and shows what would change
with the updated business rules:
1. Effective date = first appearance (hire date)
2. Agency = most recent agency (for transfers)
3. Manual overrides preserved
"""

import os
import sys
from datetime import date

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from app import create_app, db
from app.models import WageRate, TimesheetEntry
from app.utils import get_worker_hire_date, get_worker_current_agency
import pandas as pd


def analyze_business_rules_impact():
    """Analyze what would change with the updated business rules."""
    app = create_app()
    with app.app_context():
        print("Business Rules Impact Analysis")
        print("=" * 50)
        
        # Get all current wage rates
        wage_rates = WageRate.query.all()
        print(f"Total wage rate entries: {len(wage_rates)}")
        
        changes_needed = []
        
        for wage in wage_rates:
            worker_id = wage.worker_id
            current_changes = []
            
            try:
                # Get hire date and current agency
                hire_date = get_worker_hire_date(worker_id)
                current_agency = get_worker_current_agency(worker_id)
                
                # Check effective date
                if wage.effective_date != hire_date:
                    current_changes.append(f"Effective date: {wage.effective_date} → {hire_date}")
                
                # Check agency transfers
                if wage.agency != current_agency and current_agency:
                    current_changes.append(f"Agency transfer: {wage.agency} → {current_agency}")
                
                if current_changes:
                    changes_needed.append({
                        'worker_id': worker_id,
                        'changes': current_changes,
                        'current_wage': wage
                    })
                    
            except Exception as e:
                print(f"Error analyzing {worker_id}: {e}")
        
        print(f"\nWorkers needing updates: {len(changes_needed)}")
        
        # Show examples of changes
        print("\n=== Sample Changes Needed ===")
        for i, change in enumerate(changes_needed[:10]):  # Show first 10
            print(f"\n{i+1}. {change['worker_id']}:")
            for change_desc in change['changes']:
                print(f"   - {change_desc}")
        
        if len(changes_needed) > 10:
            print(f"\n... and {len(changes_needed) - 10} more workers")
        
        # Agency transfer analysis
        print("\n=== Agency Transfer Analysis ===")
        agency_transfers = [c for c in changes_needed if any('Agency transfer' in ch for ch in c['changes'])]
        print(f"Workers with agency transfers: {len(agency_transfers)}")
        
        if agency_transfers:
            print("\nExamples of agency transfers:")
            for i, transfer in enumerate(agency_transfers[:5]):
                transfer_info = [ch for ch in transfer['changes'] if 'Agency transfer' in ch][0]
                print(f"  {i+1}. {transfer['worker_id']}: {transfer_info}")
        
        # Effective date changes
        print("\n=== Effective Date Changes ===")
        date_changes = [c for c in changes_needed if any('Effective date' in ch for ch in c['changes'])]
        print(f"Workers with wrong effective dates: {len(date_changes)}")
        
        if date_changes:
            print("\nExamples of effective date corrections:")
            for i, date_change in enumerate(date_changes[:5]):
                date_info = [ch for ch in date_change['changes'] if 'Effective date' in ch][0]
                print(f"  {i+1}. {date_change['worker_id']}: {date_info}")
        
        return changes_needed


def show_sample_current_state():
    """Show a sample of current wage rate state."""
    app = create_app()
    with app.app_context():
        print("\n" + "=" * 50)
        print("=== Current Wage Rate Sample ===")
        
        # Get a few wage rates with their timesheet context
        sample_wages = WageRate.query.limit(5).all()
        
        for wage in sample_wages:
            worker_id = wage.worker_id
            
            # Get timesheet date range for this worker
            first_entry = TimesheetEntry.query.filter_by(
                worker_id=worker_id
            ).order_by(TimesheetEntry.date.asc()).first()
            
            last_entry = TimesheetEntry.query.filter_by(
                worker_id=worker_id
            ).order_by(TimesheetEntry.date.desc()).first()
            
            agencies = db.session.query(TimesheetEntry.agency).filter_by(
                worker_id=worker_id
            ).distinct().all()
            agencies_list = [a[0] for a in agencies if a[0]]
            
            print(f"\n{worker_id}:")
            print(f"  Current wage rate:")
            print(f"    Agency: {wage.agency}")
            print(f"    Effective Date: {wage.effective_date}")
            print(f"    Base Rate: ${wage.base_rate}")
            print(f"    Markup: {wage.markup:.1%}")
            
            print(f"  Timesheet data:")
            print(f"    First entry: {first_entry.date if first_entry else 'None'}")
            print(f"    Last entry: {last_entry.date if last_entry else 'None'}")
            print(f"    Agencies worked: {', '.join(agencies_list)}")


if __name__ == "__main__":
    print("Testing Updated Business Rules")
    print("This shows what would change with the new rules.")
    print()
    
    # Show current sample
    show_sample_current_state()
    
    # Analyze impact
    changes = analyze_business_rules_impact()
    
    print(f"\n{'='*50}")
    print("SUMMARY:")
    print(f"- Total workers needing updates: {len(changes)}")
    print("- Main changes: hire dates as effective dates, agency transfers")
    print("- Manual base rate overrides will be preserved")
    print("\nRun the updated wage_rate_restructure.py script to apply these changes.")