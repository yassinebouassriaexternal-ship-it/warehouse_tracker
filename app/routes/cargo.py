from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, send_file
from .. import db
from ..models import CargoVolume
from datetime import datetime
import pandas as pd
import io
from sqlalchemy import select
from ..utils import process_timesheet

cargo_bp = Blueprint('cargo', __name__)

@cargo_bp.route('/cargo/upload', methods=['GET', 'POST'])
def upload_cargo():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(url_for('cargo.upload_cargo'))
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(url_for('cargo.upload_cargo'))
        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file', 'error')
            return redirect(url_for('cargo.upload_cargo'))
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            df = pd.read_csv(stream)
            # Validate columns
            required_cols = {'Date', 'MAWB', 'Carton Number'}
            if not required_cols.issubset(df.columns):
                raise ValueError(f"Missing columns: {required_cols - set(df.columns)}")
            # Parse and insert rows
            for _, row in df.iterrows():
                # Accept both M/D/YY and MM/DD/YYYY
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
            flash(f'Successfully uploaded {file.filename} with {len(df)} records', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing file: {str(e)}', 'error')
        return redirect(url_for('cargo.upload_cargo'))
    return render_template('cargo_upload.html')

@cargo_bp.route('/cargo/relationship', methods=['GET'])
def cargo_relationship():
    # Controls: time_span, cargo_metric, worker_metric
    time_span = request.args.get('time_span', 'day')  # day, month, year
    cargo_metric = request.args.get('cargo_metric', 'mawb')  # mawb, carton
    worker_metric = request.args.get('worker_metric', 'hours')  # hours, labors

    # Query and aggregate cargo data
    df_cargo = pd.read_sql(select(CargoVolume), db.engine)
    if df_cargo.empty:
        flash('No cargo data available.', 'error')
        return render_template('cargo_relationship.html', data=None)

    # Only consider each MAWB once, on the first date it appears
    df_cargo = df_cargo.sort_values('date')
    df_cargo = df_cargo.drop_duplicates(subset=['mawb'], keep='first')

    # Aggregate cargo data
    if time_span == 'day':
        df_cargo['period'] = df_cargo['date'].astype(str)
    elif time_span == 'month':
        df_cargo['period'] = pd.to_datetime(df_cargo['date']).dt.strftime('%Y-%m')
    elif time_span == 'year':
        df_cargo['period'] = pd.to_datetime(df_cargo['date']).dt.strftime('%Y')
    else:
        df_cargo['period'] = df_cargo['date'].astype(str)

    if cargo_metric == 'mawb':
        cargo_agg = df_cargo.groupby('period')['mawb'].nunique().reset_index(name='cargo_value')
    else:
        cargo_agg = df_cargo.groupby('period')['carton_number'].sum().reset_index(name='cargo_value')

    # Aggregate worker data from timesheet
    df_timesheet = current_app.config.get('TIMESHEET_DF')
    if df_timesheet is None or df_timesheet.empty:
        flash('No timesheet data available.', 'error')
        return render_template('cargo_relationship.html', data=None)
    df_timesheet, _ = process_timesheet(df_timesheet.copy())
    df_timesheet['date'] = pd.to_datetime(df_timesheet['date'])
    if time_span == 'day':
        df_timesheet['period'] = df_timesheet['date'].dt.strftime('%Y-%m-%d')
    elif time_span == 'month':
        df_timesheet['period'] = df_timesheet['date'].dt.strftime('%Y-%m')
    elif time_span == 'year':
        df_timesheet['period'] = df_timesheet['date'].dt.strftime('%Y')
    else:
        df_timesheet['period'] = df_timesheet['date'].dt.strftime('%Y-%m-%d')

    if worker_metric == 'hours':
        worker_agg = df_timesheet.groupby('period')['daily_hours'].sum().reset_index(name='worker_value')
    else:
        worker_agg = df_timesheet.groupby('period')['worker_id'].nunique().reset_index(name='worker_value')

    # Merge cargo and worker data
    merged = pd.merge(cargo_agg, worker_agg, on='period', how='outer').fillna(0)
    merged = merged.sort_values('period')

    # Prepare data for chart
    chart_data = {
        'labels': merged['period'].tolist(),
        'cargo': merged['cargo_value'].tolist(),
        'worker': merged['worker_value'].tolist(),
        'cargo_metric': cargo_metric,
        'worker_metric': worker_metric,
        'time_span': time_span
    }
    return render_template('cargo_relationship.html', data=chart_data)

@cargo_bp.route('/cargo/export', methods=['GET'])
def export_cargo_relationship():
    # Same aggregation as in cargo_relationship
    time_span = request.args.get('time_span', 'day')
    cargo_metric = request.args.get('cargo_metric', 'mawb')
    worker_metric = request.args.get('worker_metric', 'hours')

    df_cargo = pd.read_sql(select(CargoVolume), db.engine)
    if df_cargo.empty:
        flash('No cargo data available.', 'error')
        return redirect(url_for('cargo.cargo_relationship'))

    # Only consider each MAWB once, on the first date it appears
    df_cargo = df_cargo.sort_values('date')
    df_cargo = df_cargo.drop_duplicates(subset=['mawb'], keep='first')

    if time_span == 'day':
        df_cargo['period'] = df_cargo['date'].astype(str)
    elif time_span == 'month':
        df_cargo['period'] = pd.to_datetime(df_cargo['date']).dt.strftime('%Y-%m')
    elif time_span == 'year':
        df_cargo['period'] = pd.to_datetime(df_cargo['date']).dt.strftime('%Y')
    else:
        df_cargo['period'] = df_cargo['date'].astype(str)

    if cargo_metric == 'mawb':
        cargo_agg = df_cargo.groupby('period')['mawb'].nunique().reset_index(name='cargo_value')
    else:
        cargo_agg = df_cargo.groupby('period')['carton_number'].sum().reset_index(name='cargo_value')

    df_timesheet = current_app.config.get('TIMESHEET_DF')
    if df_timesheet is None or df_timesheet.empty:
        flash('No timesheet data available.', 'error')
        return redirect(url_for('cargo.cargo_relationship'))
    from ..utils import process_timesheet
    df_timesheet, _ = process_timesheet(df_timesheet.copy())
    df_timesheet['date'] = pd.to_datetime(df_timesheet['date'])
    if time_span == 'day':
        df_timesheet['period'] = df_timesheet['date'].dt.strftime('%Y-%m-%d')
    elif time_span == 'month':
        df_timesheet['period'] = df_timesheet['date'].dt.strftime('%Y-%m')
    elif time_span == 'year':
        df_timesheet['period'] = df_timesheet['date'].dt.strftime('%Y')
    else:
        df_timesheet['period'] = df_timesheet['date'].dt.strftime('%Y-%m-%d')

    if worker_metric == 'hours':
        worker_agg = df_timesheet.groupby('period')['daily_hours'].sum().reset_index(name='worker_value')
    else:
        worker_agg = df_timesheet.groupby('period')['worker_id'].nunique().reset_index(name='worker_value')

    merged = pd.merge(cargo_agg, worker_agg, on='period', how='outer').fillna(0)
    merged = merged.sort_values('period')

    # Export as CSV
    output = io.StringIO()
    merged.to_csv(output, index=False)
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name='cargo_worker_relationship.csv'
    ) 