from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from datetime import datetime
from ..utils import process_timesheet
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
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('dashboard.dashboard'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('dashboard.dashboard'))
    
    if file and file.filename.endswith('.csv'):
        try:
            # Read the CSV into a pandas DataFrame
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            df = pd.read_csv(stream)
            
            # Store the DataFrame in the app config for later use
            current_app.config['TIMESHEET_DF'] = df
            flash(f'Successfully uploaded {file.filename} with {len(df)} entries')
        except Exception as e:
            flash(f'Error processing file: {str(e)}')
    else:
        flash('Please upload a CSV file')
    
    return redirect(url_for('dashboard.dashboard'))

@dashboard_bp.route('/export', methods=['GET'])
def export():
    df = current_app.config.get('TIMESHEET_DF')
    if df is None or df.empty:
        flash("No timesheet data available to export.")
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