from app import create_app, db
from app.models import Worker, TimesheetEntry, WageRate
import sqlite3
from sqlalchemy.exc import OperationalError

app = create_app()

def check_table_exists(model):
    try:
        model.query.first()
        return True
    except OperationalError:
        return False

with app.app_context():
    try:
        # Check which tables need to be created
        tables_needed = []
        
        if not check_table_exists(TimesheetEntry):
            print("TimesheetEntry table needs to be created")
            tables_needed.append(TimesheetEntry.__table__)
            
        if not check_table_exists(Worker):
            print("Worker table needs to be created")
            tables_needed.append(Worker.__table__)
            
        if not check_table_exists(WageRate):
            print("WageRate table needs to be created")
            tables_needed.append(WageRate.__table__)
        
        # Create all tables at once if any are needed
        if tables_needed:
            print(f"Creating {len(tables_needed)} tables...")
            db.create_all()
            print("Tables created successfully")
        else:
            print("All tables already exist")
        
        # Initialize Worker table from TimesheetEntry if needed
        try:
            worker_count_before = Worker.query.count()
            worker_ids = set([e.worker_id for e in TimesheetEntry.query.all()])
            
            for wid in worker_ids:
                if not Worker.query.filter_by(worker_id=wid).first():
                    db.session.add(Worker(worker_id=wid, is_active=True))
            
            db.session.commit()
            worker_count_after = Worker.query.count()
            
            if worker_count_after > worker_count_before:
                print(f'Added {worker_count_after - worker_count_before} new worker records.')
            else:
                print('No new worker records needed.')
                
        except Exception as e:
            print(f"Error initializing workers: {e}")
            db.session.rollback()
            
    except Exception as e:
        print(f"Error initializing database: {e}") 