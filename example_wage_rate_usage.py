#!/usr/bin/env python3
"""
Example usage of the new wage rate automation functions.

This script demonstrates how to use the wage rate automation features
to add workers and manage wage rates automatically.
"""

import os
import sys
from datetime import date, datetime

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from app import create_app, db
from app.utils import (
    add_new_worker_with_wage_rate,
    ensure_worker_wage_rate,
    calculate_wage_rate,
    get_agency_markup_for_date
)


def example_usage():
    """Demonstrate various wage rate automation features."""
    app = create_app()
    
    with app.app_context():
        print("Wage Rate Automation Examples")
        print("=" * 40)
        
        # Example 1: Calculate wage rate for a position and agency
        print("\n1. Calculate wage rate for forklift driver at JJ Staffing:")
        try:
            base_rate, markup, total_rate = calculate_wage_rate('forklift driver', 'JJ Staffing')
            print(f"   Base rate: ${base_rate:.2f}/hr")
            print(f"   Markup: {markup:.1%}")
            print(f"   Total rate: ${total_rate:.2f}/hr")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Example 2: Get agency markup for a specific date
        print("\n2. Get agency markup for Stride Staffing:")
        try:
            markup = get_agency_markup_for_date('Stride Staffing')
            print(f"   Current markup: {markup:.1%}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Example 3: Add a new worker with automatic wage rate
        print("\n3. Add new worker with automatic wage rate:")
        try:
            result = add_new_worker_with_wage_rate(
                worker_id='TEST001',
                position='general labor',
                agency_name='JJ Staffing',
                name='John Test Worker'
            )
            print(f"   Status: {result['status']}")
            print(f"   Message: {result['message']}")
        except Exception as e:
            print(f"   Error: {e}")
            # Rollback on error
            db.session.rollback()
        
        # Example 4: Ensure wage rate for existing worker
        print("\n4. Ensure wage rate for existing worker:")
        try:
            wage_rate = ensure_worker_wage_rate(
                worker_id='TEST001',
                position='forklift driver',  # Changed position
                agency_name='JJ Staffing',
                effective_date=date.today()
            )
            print(f"   Updated worker TEST001 to forklift driver position")
            print(f"   New base rate: ${wage_rate.base_rate:.2f}/hr")
            print(f"   Markup: {wage_rate.markup:.1%}")
        except Exception as e:
            print(f"   Error: {e}")
            db.session.rollback()
        
        # Clean up test data
        print("\n5. Cleaning up test data...")
        try:
            from app.models import Worker, WageRate
            
            # Remove test worker and wage rates
            test_worker = Worker.query.filter_by(worker_id='TEST001').first()
            if test_worker:
                # Remove associated wage rates
                WageRate.query.filter_by(worker_id='TEST001').delete()
                db.session.delete(test_worker)
                db.session.commit()
                print("   Test data cleaned up successfully")
            else:
                print("   No test data to clean up")
                
        except Exception as e:
            print(f"   Error cleaning up: {e}")
            db.session.rollback()


if __name__ == "__main__":
    example_usage()