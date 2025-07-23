import os
import sys

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Import the db and models from the app
from app import create_app, db
from app.models import Worker, WageRate

def activate_jj_workers():
    """Activate more JJ Staffing workers"""
    app = create_app()
    with app.app_context():
        # Find JJ Staffing workers
        jj_workers = db.session.query(Worker).join(
            WageRate, Worker.worker_id == WageRate.worker_id
        ).filter(
            WageRate.agency == 'JJ Staffing'
        ).all()
        
        activated_count = 0
        for worker in jj_workers:
            if not worker.is_active:
                worker.is_active = True
                activated_count += 1
                if activated_count >= 10:  # Activate up to 10 workers
                    break
        
        db.session.commit()
        print(f"Activated {activated_count} JJ Staffing workers.")
        
        # Count active JJ Staffing workers
        active_count = db.session.query(Worker).join(
            WageRate, Worker.worker_id == WageRate.worker_id
        ).filter(
            WageRate.agency == 'JJ Staffing',
            Worker.is_active == True
        ).count()
        
        print(f"Total active JJ Staffing workers: {active_count}")

if __name__ == "__main__":
    activate_jj_workers() 