import os
import sys
from sqlalchemy import inspect
from datetime import datetime, timedelta

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Import the db and models from the app
from app import create_app, db
from app.models import TimesheetEntry, WageRate, Worker, Schedule

def update_db():
    """Update the database schema without dropping existing tables"""
    app = create_app()
    with app.app_context():
        # Get the inspector
        inspector = inspect(db.engine)
        
        # Check if Schedule table exists
        if 'schedule' not in inspector.get_table_names():
            print("Creating Schedule table...")
            # Create only the Schedule table
            Schedule.__table__.create(db.engine)
            print("Schedule table created successfully.")
        else:
            print("Schedule table already exists.")

def create_sample_schedules():
    """Create some sample schedules for active workers"""
    app = create_app()
    with app.app_context():
        # Get active workers
        workers = Worker.query.filter_by(is_active=True).limit(5).all()
        
        if not workers:
            print("No active workers found.")
            return
        
        # Get today's date and calculate dates for the week
        today = datetime.now().date()
        monday = today - timedelta(days=today.weekday())
        
        # Create schedules for the next 7 days
        for i in range(7):
            schedule_date = monday + timedelta(days=i)
            
            for worker in workers:
                # Get worker's agency from WageRate
                wage_info = WageRate.query.filter_by(worker_id=worker.worker_id).order_by(WageRate.effective_date.desc()).first()
                agency = wage_info.agency if wage_info else None
                
                # Check if schedule already exists
                existing_schedule = Schedule.query.filter_by(
                    worker_id=worker.worker_id,
                    date=schedule_date
                ).first()
                
                if not existing_schedule and i < 5:  # Only schedule for weekdays (Monday to Friday)
                    # Create a new schedule
                    schedule = Schedule(
                        worker_id=worker.worker_id,
                        date=schedule_date,
                        time_in=datetime.strptime('08:00', '%H:%M').time(),
                        time_out=datetime.strptime('16:30', '%H:%M').time(),
                        agency=agency,
                        is_confirmed=(i < 2)  # Confirm only for the first two days
                    )
                    db.session.add(schedule)
        
        db.session.commit()
        print("Sample schedules created.")

if __name__ == "__main__":
    update_db()
    create_sample_schedules() 