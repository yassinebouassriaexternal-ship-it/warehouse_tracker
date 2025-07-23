import os
import sys

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Import the db and models from the app
from app import create_app, db
from app.models import Schedule

def clear_schedules():
    """Clear all schedules from the database"""
    app = create_app()
    with app.app_context():
        # Count schedules before deletion
        count_before = Schedule.query.count()
        
        # Delete all schedules
        Schedule.query.delete()
        
        # Commit the changes
        db.session.commit()
        
        # Verify deletion
        count_after = Schedule.query.count()
        
        print(f"Deleted {count_before} schedules. Remaining: {count_after}")

if __name__ == "__main__":
    clear_schedules() 