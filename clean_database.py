#!/usr/bin/env python3
"""
Database cleaning script to remove all existing data from the warehouse tracker database.
This script will:
1. Clear all TimesheetEntry records
2. Clear all WageRate records  
3. Clear all Worker records
4. Keep table structure intact for fresh data upload
"""

from app import create_app, db
from app.models import TimesheetEntry, WageRate, Worker
import sys

def count_records():
    """Count current records in all tables."""
    app = create_app()
    with app.app_context():
        timesheet_count = TimesheetEntry.query.count()
        wage_rate_count = WageRate.query.count()
        worker_count = Worker.query.count()
        
        print(f"Current database contents:")
        print(f"  📋 TimesheetEntry records: {timesheet_count}")
        print(f"  💰 WageRate records: {wage_rate_count}")
        print(f"  👥 Worker records: {worker_count}")
        print(f"  📊 Total records: {timesheet_count + wage_rate_count + worker_count}")
        
        return timesheet_count + wage_rate_count + worker_count

def clean_database(dry_run=True):
    """Clean all data from the database tables."""
    app = create_app()
    with app.app_context():
        total_records = count_records()
        
        if total_records == 0:
            print("\n✅ Database is already clean! No records to remove.")
            return
        
        if not dry_run:
            print("\n🧹 CLEANING DATABASE...")
        else:
            print("\n👀 DRY RUN - showing what would be cleaned:")
        
        try:
            # Count records before deletion
            timesheet_count = TimesheetEntry.query.count()
            wage_rate_count = WageRate.query.count()
            worker_count = Worker.query.count()
            
            if not dry_run:
                # Delete all records (order matters due to relationships)
                print("  🗑️  Deleting all TimesheetEntry records...")
                TimesheetEntry.query.delete()
                
                print("  🗑️  Deleting all WageRate records...")
                WageRate.query.delete()
                
                print("  🗑️  Deleting all Worker records...")
                Worker.query.delete()
                
                # Commit all changes
                db.session.commit()
                
                print(f"\n✅ Successfully cleaned database!")
                print(f"   Removed {timesheet_count} timesheet entries")
                print(f"   Removed {wage_rate_count} wage rate records")
                print(f"   Removed {worker_count} worker records")
                print(f"   Total removed: {total_records} records")
                print("\n🎯 Database is ready for fresh data upload!")
                
            else:
                print(f"  Would delete {timesheet_count} TimesheetEntry records")
                print(f"  Would delete {wage_rate_count} WageRate records")
                print(f"  Would delete {worker_count} Worker records")
                print(f"\n📊 Summary: Would remove {total_records} total records")
                print("Run with --clean flag to apply changes")
                
        except Exception as e:
            if not dry_run:
                db.session.rollback()
                print(f"\n❌ Error occurred: {e}")
                print("Changes have been rolled back.")
            else:
                print(f"\n❌ Error during dry run: {e}")

def backup_database():
    """Create a simple backup of current data."""
    app = create_app()
    with app.app_context():
        import pandas as pd
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        try:
            # Export timesheet entries
            timesheet_data = []
            for entry in TimesheetEntry.query.all():
                timesheet_data.append({
                    'worker_id': entry.worker_id,
                    'date': entry.date.isoformat(),
                    'time_in': entry.time_in.isoformat(),
                    'time_out': entry.time_out.isoformat(),
                    'lunch_minutes': entry.lunch_minutes,
                    'agency': entry.agency
                })
            
            if timesheet_data:
                df_timesheet = pd.DataFrame(timesheet_data)
                filename = f"backup_timesheet_{timestamp}.csv"
                df_timesheet.to_csv(filename, index=False)
                print(f"📁 Timesheet backup saved: {filename}")
            
            # Export worker data
            worker_data = []
            for worker in Worker.query.all():
                worker_data.append({
                    'worker_id': worker.worker_id,
                    'name': worker.name,
                    'is_active': worker.is_active
                })
            
            if worker_data:
                df_workers = pd.DataFrame(worker_data)
                filename = f"backup_workers_{timestamp}.csv"
                df_workers.to_csv(filename, index=False)
                print(f"👥 Workers backup saved: {filename}")
            
            # Export wage rate data
            wage_data = []
            for rate in WageRate.query.all():
                wage_data.append({
                    'worker_id': rate.worker_id,
                    'base_rate': rate.base_rate,
                    'role': rate.role,
                    'agency': rate.agency,
                    'markup': rate.markup,
                    'effective_date': rate.effective_date.isoformat() if rate.effective_date else None
                })
            
            if wage_data:
                df_wages = pd.DataFrame(wage_data)
                filename = f"backup_wages_{timestamp}.csv"
                df_wages.to_csv(filename, index=False)
                print(f"💰 Wage rates backup saved: {filename}")
                
            print(f"\n✅ Backup completed with timestamp: {timestamp}")
            
        except Exception as e:
            print(f"❌ Backup failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--clean":
            print("🚨 RUNNING IN CLEAN MODE - This will permanently delete all data!")
            print("Make sure you have a backup of your data before proceeding.")
            response = input("Are you sure you want to continue? (y/N): ")
            if response.lower() == 'y':
                clean_database(dry_run=False)
            else:
                print("Operation cancelled.")
        elif sys.argv[1] == "--backup":
            print("📁 Creating backup of current database...")
            backup_database()
        elif sys.argv[1] == "--backup-and-clean":
            print("📁 Creating backup first, then cleaning database...")
            backup_database()
            print("\n" + "="*50)
            response = input("\nBackup completed. Proceed with cleaning? (y/N): ")
            if response.lower() == 'y':
                clean_database(dry_run=False)
            else:
                print("Cleaning cancelled. Backup files have been saved.")
        else:
            print("Unknown option. Use --clean, --backup, or --backup-and-clean")
    else:
        print("Running in dry-run mode...")
        clean_database(dry_run=True)
        print("\nOptions:")
        print("  --clean              : Clean database (DESTRUCTIVE)")
        print("  --backup            : Create backup files only")
        print("  --backup-and-clean  : Create backup then clean database") 