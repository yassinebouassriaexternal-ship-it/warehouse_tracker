from . import db
from datetime import date

class CargoVolume(db.Model):
    __tablename__ = 'cargo_volume'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    mawb = db.Column(db.String(64), nullable=False, index=True)
    carton_number = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'<CargoVolume {self.date} {self.mawb} {self.carton_number}>' 