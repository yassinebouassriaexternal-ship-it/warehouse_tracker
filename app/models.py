from . import db
from datetime import date

class TimesheetEntry(db.Model):
    __tablename__ = 'timesheet_entry'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.String(64), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    time_in = db.Column(db.Time, nullable=False)
    time_out = db.Column(db.Time, nullable=False)
    lunch_minutes = db.Column(db.Integer, default=30)
    agency = db.Column(db.String(128), nullable=True)

    def __repr__(self):
        return f'<TimesheetEntry {self.worker_id} {self.date} {self.time_in}-{self.time_out}>'

class WageRate(db.Model):
    __tablename__ = 'wage_rate'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.String(64), nullable=False, index=True)
    base_rate = db.Column(db.Float, nullable=True)  # e.g., 16 or 18
    role = db.Column(db.String(64), nullable=True)   # e.g., 'general', 'forklift'
    agency = db.Column(db.String(128), nullable=True)
    markup = db.Column(db.Float, nullable=True)      # e.g., 0.25 for 25%
    effective_date = db.Column(db.Date, nullable=True)  # Now required

    def __repr__(self):
        return f'<WageRate {self.worker_id} {self.base_rate} {self.markup}>'

class Worker(db.Model):
    __tablename__ = 'worker'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f'<Worker {self.worker_id} {"Active" if self.is_active else "Inactive"}>' 