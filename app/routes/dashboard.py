from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from datetime import datetime
from ..utils import process_timesheet
from ..validation import validate_timesheet_data
from ..models import CargoVolume
from .. import db
import pandas as pd
import io

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/', methods=['GET'])
def dashboard():
    df = current_app.config.get('TIMESHEET_DF')
    if df is None or df.empty:
        flash("No timesheet data available. Please upload CSV.")
        return render_template('dashboard.html', summary=None, worker_filter='', week_filter='')

    # Process the timesheet data
    processed_df, summary = process_timesheet(df.copy())

    # Apply filters
    worker_filter = request.args.get('worker', '')
    week_filter = request.args.get('week', '')
    if worker_filter:
        summary = summary[summary['worker_id'] == worker_filter]
    if week_filter:
        try:
            week_int = int(week_filter)
            summary = summary[summary['week'] == week_int]
        except ValueError:
            pass
    else:
        # Default: show current week
        current_week = datetime.today().isocalendar()[1]
        summary = summary[summary['week'] == current_week]

    return render_template('dashboard.html',
                           summary=summary,
                           worker_filter=worker_filter,
                           week_filter=week_filter)

@dashboard_bp.route('/upload', methods=['POST'])
def upload():
    timesheet_file = request.files.get('timesheet_file')
    cargo_file = request.files.get('cargo_file')
    did_upload = False

    # Handle timesheet upload
    if timesheet_file and timesheet_file.filename:
        if not timesheet_file.filename.endswith('.csv'):
            flash('Please upload a CSV file for timesheet.', 'error')
        else:
            try:
                stream = io.StringIO(timesheet_file.stream.read().decode("UTF8"), newline=None)
                df = pd.read_csv(stream)
                validate_timesheet_data(df)
                current_app.config['TIMESHEET_DF'] = df
                flash(f'Successfully uploaded {timesheet_file.filename} with {len(df)} entries', 'success')
                did_upload = True
            except ValueError as e:
                flash(f'Validation error (timesheet): {str(e)}', 'error')
            except Exception as e:
                flash(f'Error processing timesheet file: {str(e)}', 'error')

    # Handle cargo upload
    if cargo_file and cargo_file.filename:
        if not cargo_file.filename.endswith('.csv'):
            flash('Please upload a CSV file for cargo volume.', 'error')
        else:
            try:
                stream = io.StringIO(cargo_file.stream.read().decode("UTF8"), newline=None)
                df = pd.read_csv(stream)
                required_cols = {'Date', 'MAWB', 'Carton Number'}
                if not required_cols.issubset(df.columns):
                    raise ValueError(f"Missing columns: {required_cols - set(df.columns)}")
                for _, row in df.iterrows():
                    date_str = str(row['Date'])
                    try:
                        date = datetime.strptime(date_str, '%m/%d/%Y').date()
                    except ValueError:
                        try:
                            date = datetime.strptime(date_str, '%m/%d/%y').date()
                        except ValueError:
                            raise ValueError(f"Invalid date format: {date_str}. Expected MM/DD/YYYY or M/D/YY")
                    mawb = str(row['MAWB'])
                    carton_number = int(row['Carton Number'])
                    cargo = CargoVolume(date=date, mawb=mawb, carton_number=carton_number)
                    db.session.add(cargo)
                db.session.commit()
                flash(f'Successfully uploaded {cargo_file.filename} with {len(df)} cargo records', 'success')
                did_upload = True
            except Exception as e:
                db.session.rollback()
                flash(f'Error processing cargo file: {str(e)}', 'error')

    if not did_upload:
        flash('No file selected for upload.', 'error')

    return redirect(url_for('dashboard.dashboard'))

@dashboard_bp.route('/export', methods=['GET'])
def export():
    df = current_app.config.get('TIMESHEET_DF')
    if df is None or df.empty:
        flash("No timesheet data available to export.", 'error')
        return redirect(url_for('dashboard.dashboard'))
    # Convert DataFrame to CSV
    output = io.StringIO()
    df.to_csv(output, index=False)
    csv_data = output.getvalue()
    # Create a response with the CSV data
    from flask import Response
    response = Response(csv_data, mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=timesheet_export.csv"
    return response