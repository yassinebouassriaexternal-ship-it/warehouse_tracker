from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from datetime import datetime
from ..utils import process_timesheet, forecast_labor_needs
from ..validation import validate_timesheet_data
from ..models import TimesheetEntry, WageRate, Worker
from .. import db
import pandas as pd
import io

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/', methods=['GET'])
def dashboard():
    show_all = request.args.get('show_all', '0') == '1'
    df = current_app.config.get('TIMESHEET_DF')
    if df is None or df.empty:
        # Load from database if not in memory
        entries = TimesheetEntry.query.all()
        if not entries:
            flash("No timesheet data available. Please upload CSV.")
            return render_template('dashboard.html', summary=None, worker_filter='', week_filter='', predictions=None, show_all=show_all, is_forecast=False)
        # Convert to DataFrame
        df = pd.DataFrame([
            {
                'worker_id': e.worker_id,
                'date': e.date,
                'time_in': e.time_in,
                'time_out': e.time_out,
                'lunch_minutes': e.lunch_minutes,
                'Agency': e.agency
            }
            for e in entries
        ])
        current_app.config['TIMESHEET_DF'] = df

    # Process the timesheet data
    processed_df, summary = process_timesheet(df.copy())

    # Filter to only active workers unless show_all is set
    if not show_all:
        active_workers = {w.worker_id for w in Worker.query.filter_by(is_active=True).all()}
        summary = summary[summary['worker_id'].isin(active_workers)]

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
                           week_filter=week_filter,
                           predictions=None,
                           show_all=show_all,
                           is_forecast=False)

@dashboard_bp.route('/upload', methods=['POST'])
def upload():
    timesheet_file = request.files.get('timesheet_file')
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
                # Persist to database
                inserted = 0
                for _, row in df.iterrows():
                    # Parse date and time
                    worker_id = str(row['worker_id']).strip()
                    date_val = pd.to_datetime(row['date']).date()
                    time_in_val = pd.to_datetime(str(row['time_in'])).time()
                    time_out_val = pd.to_datetime(str(row['time_out'])).time()
                    lunch_minutes = int(row['lunch_minutes']) if 'lunch_minutes' in row and not pd.isnull(row['lunch_minutes']) else 30
                    agency = row['Agency'] if 'Agency' in row and not pd.isnull(row['Agency']) else None
                    # Check for duplicate
                    exists = TimesheetEntry.query.filter_by(worker_id=worker_id, date=date_val, time_in=time_in_val).first()
                    if not exists:
                        entry = TimesheetEntry(
                            worker_id=worker_id,
                            date=date_val,
                            time_in=time_in_val,
                            time_out=time_out_val,
                            lunch_minutes=lunch_minutes,
                            agency=agency
                        )
                        db.session.add(entry)
                        inserted += 1
                        # --- Sync Worker table ---
                        worker_exists = Worker.query.filter_by(worker_id=worker_id).first()
                        if not worker_exists:
                            worker = Worker(worker_id=worker_id, is_active=True)
                            db.session.add(worker)
                        # --- Sync WageRate table ---
                        wage_rate_exists = WageRate.query.filter_by(worker_id=worker_id, agency=agency).first()
                        if not wage_rate_exists:
                            wage_rate = WageRate(worker_id=worker_id, agency=agency, base_rate=None, role=None, markup=None, effective_date=None)
                            db.session.add(wage_rate)
                db.session.commit()
                # Also update in-memory DataFrame for analytics
                df['worker_id'] = df['worker_id'].astype(str).str.strip()
                current_app.config['TIMESHEET_DF'] = df
                flash(f'Successfully uploaded {timesheet_file.filename} with {inserted} new entries', 'success')
                did_upload = True

                # --- Always sync wage_rate table with all unique (worker_id, agency) pairs ---
                unique_worker_agency = db.session.query(TimesheetEntry.worker_id, TimesheetEntry.agency).distinct().all()
                added_wagerates = 0
                for worker_id, agency in unique_worker_agency:
                    wage_rate_exists = WageRate.query.filter_by(worker_id=worker_id, agency=agency).first()
                    if not wage_rate_exists:
                        wage_rate = WageRate(worker_id=worker_id, agency=agency, base_rate=None, role=None, markup=None, effective_date=None)
                        db.session.add(wage_rate)
                        added_wagerates += 1
                if added_wagerates > 0:
                    db.session.commit()
            except ValueError as e:
                flash(f'Validation error (timesheet): {str(e)}', 'error')
            except Exception as e:
                db.session.rollback()
                flash(f'Error processing timesheet file: {str(e)}', 'error')



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

@dashboard_bp.route('/wage_rates', methods=['GET', 'POST'])
def wage_rates():
    show_all = request.args.get('show_all', '0') == '1'
    from ..models import WageRate, TimesheetEntry, Worker
    agency_filter = request.args.get('agency', '')
    worker_agency = {}
    all_entries = TimesheetEntry.query.all()
    for e in all_entries:
        if e.worker_id not in worker_agency:
            worker_agency[e.worker_id] = e.agency
    # Filter workers by active status unless show_all
    if not show_all:
        active_workers = {w.worker_id for w in Worker.query.filter_by(is_active=True).all()}
        filtered_workers = [w for w, a in worker_agency.items() if (not agency_filter or (a == agency_filter)) and w in active_workers]
    else:
        filtered_workers = [w for w, a in worker_agency.items() if not agency_filter or (a == agency_filter)]
    # Get all wage rates (all records, not just latest)
    query = WageRate.query
    if agency_filter:
        query = query.filter(WageRate.agency == agency_filter)
    all_wage_rates = query.order_by(WageRate.worker_id, WageRate.effective_date.desc()).all()
    # Build list of dicts for template (show all rates)
    workers = []
    for rate in all_wage_rates:
        if show_all or rate.worker_id in filtered_workers:
            workers.append({
                'id': rate.id,
                'worker_id': rate.worker_id,
                'base_rate': rate.base_rate,
                'role': rate.role,
                'agency': rate.agency,
                'markup': rate.markup,
                'effective_date': rate.effective_date.strftime('%Y-%m-%d') if rate.effective_date else ''
            })
    agencies = sorted(set(a for a in worker_agency.values() if a))
    if request.method == 'POST':
        worker_id = request.form.get('worker_id').strip()
        base_rate = float(request.form.get('base_rate'))
        role = request.form.get('role').strip() or None
        agency = request.form.get('agency').strip() or None
        effective_date_str = request.form.get('effective_date')
        if not effective_date_str:
            flash('Effective date is required.', 'error')
            return redirect(url_for('dashboard.wage_rates', agency=agency_filter, show_all=int(show_all)))
        effective_date = pd.to_datetime(effective_date_str).date()
        if agency in ('JJ', 'JJ Staffing'):
            markup = 0.25
        elif agency in ('Stride', 'Stride Staffing'):
            markup = 0.3
        else:
            markup = 0.0
        rate = WageRate(worker_id=worker_id, base_rate=base_rate, role=role, agency=agency, markup=markup, effective_date=effective_date)
        db.session.add(rate)
        db.session.commit()
        flash(f'Wage rate for {worker_id} on {effective_date} saved.', 'success')
        return redirect(url_for('dashboard.wage_rates', agency=agency_filter, show_all=int(show_all)))
    return render_template('wage_rates.html', workers=workers, agencies=agencies, agency_filter=agency_filter, show_all=show_all)

@dashboard_bp.route('/wage_rates/edit/<int:wage_rate_id>', methods=['GET', 'POST'])
def edit_wage_rate(wage_rate_id):
    wage_rate = WageRate.query.get_or_404(wage_rate_id)
    show_all = request.args.get('show_all', '0')
    agency_filter = request.args.get('agency', '')
    if request.method == 'POST':
        wage_rate.worker_id = request.form.get('worker_id').strip()
        wage_rate.base_rate = float(request.form.get('base_rate'))
        wage_rate.role = request.form.get('role').strip() or None
        wage_rate.agency = request.form.get('agency').strip() or None
        effective_date_str = request.form.get('effective_date')
        if not effective_date_str:
            flash('Effective date is required.', 'error')
            return redirect(url_for('dashboard.edit_wage_rate', wage_rate_id=wage_rate_id, agency=agency_filter, show_all=show_all))
        wage_rate.effective_date = pd.to_datetime(effective_date_str).date()
        # Set markup automatically based on agency
        if wage_rate.agency in ('JJ', 'JJ Staffing'):
            wage_rate.markup = 0.25
        elif wage_rate.agency in ('Stride', 'Stride Staffing'):
            wage_rate.markup = 0.3
        else:
            wage_rate.markup = 0.0
        db.session.commit()
        flash('Wage rate updated.', 'success')
        return redirect(url_for('dashboard.wage_rates', agency=agency_filter, show_all=show_all))
    return render_template('edit_wage_rate.html', wage_rate=wage_rate, agency=agency_filter, show_all=show_all)

@dashboard_bp.route('/wage_rates/delete/<int:wage_rate_id>', methods=['POST'])
def delete_wage_rate(wage_rate_id):
    wage_rate = WageRate.query.get_or_404(wage_rate_id)
    db.session.delete(wage_rate)
    db.session.commit()
    flash('Wage rate deleted.', 'success')
    return redirect(url_for('dashboard.wage_rates'))

@dashboard_bp.route('/predict', methods=['GET'])
def predict():
    show_all = request.args.get('show_all', '0') == '1'
    df = current_app.config.get('TIMESHEET_DF')
    if df is None or df.empty:
        entries = TimesheetEntry.query.all()
        if not entries:
            flash("No timesheet data available. Please upload CSV.")
            return render_template('dashboard.html', summary=None, predictions=None, worker_filter='', week_filter='', show_all=show_all, is_forecast=True)
        df = pd.DataFrame([
            {
                'worker_id': e.worker_id,
                'date': e.date,
                'time_in': e.time_in,
                'time_out': e.time_out,
                'lunch_minutes': e.lunch_minutes,
                'Agency': e.agency
            }
            for e in entries
        ])
        current_app.config['TIMESHEET_DF'] = df
    processed_df, _ = process_timesheet(df.copy())
    predictions = forecast_labor_needs(processed_df)
    if not show_all:
        active_workers = {w.worker_id for w in Worker.query.filter_by(is_active=True).all()}
        predictions = predictions[predictions['worker_id'].isin(active_workers)]
    return render_template('dashboard.html', summary=None, predictions=predictions, worker_filter='', week_filter='', show_all=show_all, is_forecast=True)

@dashboard_bp.route('/workers', methods=['GET', 'POST'])
def manage_workers():
    from ..models import Worker
    if request.method == 'POST':
        action = request.form.get('action')
        worker_id = request.form.get('worker_id')
        worker = Worker.query.filter_by(worker_id=worker_id).first()
        if worker:
            if action == 'toggle_active':
                worker.is_active = not worker.is_active
            elif action == 'edit_name':
                new_name = request.form.get('name', '').strip()
                worker.name = new_name
            db.session.commit()
        return redirect(url_for('dashboard.manage_workers'))
    workers = Worker.query.order_by(Worker.is_active.desc(), Worker.worker_id).all()
    return render_template('manage_workers.html', workers=workers)