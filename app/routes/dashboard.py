from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from datetime import datetime
from ..utils import process_timesheet, forecast_labor_needs
from ..validation import validate_timesheet_data, normalize_position, get_base_rate_for_position, get_markup_for_agency
from ..models import TimesheetEntry, WageRate, Worker
from .. import db
import pandas as pd
import io
import numpy as np

dashboard_bp = Blueprint('dashboard', __name__)

def prepare_weekly_chart_data(summary, week_filter):
    """
    Prepare data for the weekly summary visualization chart.
    Returns aggregated totals for current week and previous week comparison.
    """
    current_week = int(week_filter) if week_filter else datetime.today().isocalendar()[1]
    previous_week = current_week - 1 if current_week > 1 else 52
    
    # Get the full DataFrame for comparison
    df = current_app.config.get('TIMESHEET_DF')
    if df is None or df.empty:
        return {
            'weeks': [f'Week {previous_week}', f'Week {current_week}'],
            'current_regular': 0,
            'current_overtime': 0,
            'previous_regular': 0,
            'previous_overtime': 0,
            'current_week': current_week,
            'previous_week': previous_week
        }
    
    # Process the full timesheet to get both weeks
    processed_df, full_summary = process_timesheet(df.copy())
    
    # Calculate totals for current week
    current_week_data = full_summary[full_summary['week'] == current_week]
    current_total_regular = 0
    current_total_overtime = 0
    
    for _, row in current_week_data.iterrows():
        regular = min(row['total_hours'], 40.0)
        overtime = max(row['total_hours'] - 40.0, 0.0)
        current_total_regular += regular
        current_total_overtime += overtime
    
    # Calculate totals for previous week
    previous_week_data = full_summary[full_summary['week'] == previous_week]
    previous_total_regular = 0
    previous_total_overtime = 0
    
    for _, row in previous_week_data.iterrows():
        regular = min(row['total_hours'], 40.0)
        overtime = max(row['total_hours'] - 40.0, 0.0)
        previous_total_regular += regular
        previous_total_overtime += overtime
    
    return {
        'weeks': [f'Week {previous_week}', f'Week {current_week}'],
        'current_regular': current_total_regular,
        'current_overtime': current_total_overtime,
        'previous_regular': previous_total_regular,
        'previous_overtime': previous_total_overtime,
        'current_week': current_week,
        'previous_week': previous_week
    }

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
                'agency': e.agency
            }
            for e in entries
        ])
        # Normalize agency column name
        if 'agency' in df.columns and 'Agency' not in df.columns:
            df['Agency'] = df['agency']
        current_app.config['TIMESHEET_DF'] = df

    # Process the timesheet data
    processed_df, summary_full = process_timesheet(df.copy())
    # Ensure summary has 'Agency' column for filtering
    if 'Agency' in df.columns and 'Agency' not in summary_full.columns:
        summary_full = summary_full.merge(df[['worker_id', 'Agency']].drop_duplicates(), on='worker_id', how='left')

    # --- Metrics Calculation (use full summary for hours, filtered summary for workers) ---
    current_week_num = int(request.args.get('week', '') or datetime.today().isocalendar()[1])
    last_week_num = current_week_num - 1 if current_week_num > 1 else 52
    total_hours_current = summary_full[summary_full['week'] == current_week_num]['total_hours'].sum()
    total_hours_last = summary_full[summary_full['week'] == last_week_num]['total_hours'].sum()
    week_over_week_change = ((total_hours_current - total_hours_last) / total_hours_last * 100) if total_hours_last else np.nan
    # Now apply filters for table display
    summary = summary_full.copy()
    if not show_all:
        active_workers = {w.worker_id for w in Worker.query.filter_by(is_active=True).all()}
        summary = summary[summary['worker_id'].isin(active_workers)]
    agency_filter = request.args.get('agency', '')
    worker_filter = request.args.get('worker', '')
    week_filter = request.args.get('week', '')
    week_explicitly_selected = bool(week_filter)
    week_auto_selected = False
    if week_filter:
        try:
            week_int = int(week_filter)
            summary = summary[summary['week'] == week_int]
        except ValueError:
            pass
    else:
        available_weeks = sorted(summary['week'].unique(), reverse=True)
        if available_weeks:
            selected_week = available_weeks[0]
            week_auto_selected = (selected_week != datetime.today().isocalendar()[1])
        else:
            selected_week = datetime.today().isocalendar()[1]
        summary = summary[summary['week'] == selected_week]
        week_filter = str(selected_week)
    if agency_filter:
        if 'Agency' in summary.columns:
            summary = summary[summary['Agency'] == agency_filter]
    if worker_filter:
        summary = summary[summary['worker_id'] == worker_filter]
    # Calculate num_workers and avg_hours_per_worker from filtered summary
    num_workers = summary['worker_id'].nunique() if 'worker_id' in summary.columns else 0
    avg_hours_per_worker = (summary['total_hours'].sum() / num_workers) if num_workers else 0
    max_hours = summary['total_hours'].max() if not summary.empty else 0
    min_hours = summary['total_hours'].min() if not summary.empty else 0
    total_overtime_hours = sum(max(row['total_hours'] - 40, 0) for _, row in summary.iterrows())
    metrics = {
        'total_hours_current': total_hours_current,
        'total_hours_last': total_hours_last,
        'week_over_week_change': week_over_week_change,
        'total_overtime_hours': total_overtime_hours,
        'num_workers': num_workers,
        'avg_hours_per_worker': avg_hours_per_worker,
        'max_hours': max_hours,
        'min_hours': min_hours
    }

    # Apply filters
    worker_filter = request.args.get('worker', '')
    week_filter = request.args.get('week', '')
    if worker_filter:
        summary = summary[summary['worker_id'] == worker_filter]
    
    # Apply week filter first
    week_explicitly_selected = bool(week_filter)
    week_auto_selected = False
    if week_filter:
        try:
            week_int = int(week_filter)
            summary = summary[summary['week'] == week_int]
        except ValueError:
            pass
    else:
        # Auto-select week: show current week if it has data, otherwise show last week with data
        current_week = datetime.today().isocalendar()[1]
        available_weeks = sorted(summary['week'].unique(), reverse=True)
        
        if available_weeks:
            if current_week in available_weeks:
                # Current week has data, show it
                selected_week = current_week
            else:
                # Current week has no data, show the most recent week with data
                selected_week = available_weeks[0]
                week_auto_selected = True
        else:
            # No data available, default to current week
            selected_week = current_week
            
        summary = summary[summary['week'] == selected_week]
        week_filter = str(selected_week)  # Update week_filter for template
    
    # Filter to only active workers unless show_all is set
    # Show all workers who worked in the week if a specific week was selected
    # Only filter by active status when showing default current week view
    if not show_all and not week_explicitly_selected:
        active_workers = {w.worker_id for w in Worker.query.filter_by(is_active=True).all()}
        summary = summary[summary['worker_id'].isin(active_workers)]

    # Prepare visualization data for the selected week
    chart_data = prepare_weekly_chart_data(summary, week_filter)

    # Get list of available agencies for filter dropdown
    agencies = sorted(df['Agency'].dropna().unique().tolist()) if 'Agency' in df.columns else []

    all_weeks = sorted(summary_full['week'].unique(), reverse=True)
    return render_template('dashboard.html',
                           summary=summary,
                           worker_filter=worker_filter,
                           week_filter=week_filter,
                           predictions=None,
                           show_all=show_all,
                           is_forecast=False,
                           chart_data=chart_data,
                           week_auto_selected=week_auto_selected,
                           current_week=datetime.today().isocalendar()[1])

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
                # Accept both 'agency' and 'Agency' as the agency column
                if 'Agency' not in df.columns and 'agency' in df.columns:
                    df['Agency'] = df['agency']
                validate_timesheet_data(df)
                # Collect worker first appearance dates for wage rate effective dates
                worker_first_dates = {}
                
                # First pass: determine the first appearance date for each worker
                for _, row in df.iterrows():
                    worker_id = str(row['worker_id']).strip()
                    date_val = pd.to_datetime(row['date']).date()
                    if worker_id not in worker_first_dates or date_val < worker_first_dates[worker_id]:
                        worker_first_dates[worker_id] = date_val
                
                # Persist to database
                inserted = 0
                wage_rates_created = 0
                for _, row in df.iterrows():
                    # Parse date and time
                    worker_id = str(row['worker_id']).strip()
                    date_val = pd.to_datetime(row['date']).date()
                    time_in_val = pd.to_datetime(str(row['time_in'])).time()
                    time_out_val = pd.to_datetime(str(row['time_out'])).time()
                    lunch_minutes = int(row['lunch_minutes']) if 'lunch_minutes' in row and not pd.isnull(row['lunch_minutes']) else 30
                    agency = row['agency'] if 'agency' in row and not pd.isnull(row['agency']) else None
                    position = normalize_position(row['position']) if 'position' in row and not pd.isnull(row['position']) else None
                    
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
                        
                        # --- Sync WageRate table with automatic rate setting ---
                        wage_rate_exists = WageRate.query.filter_by(worker_id=worker_id, agency=agency).first()
                        if not wage_rate_exists and position:
                            try:
                                base_rate = get_base_rate_for_position(position)
                                markup = get_markup_for_agency(agency)
                                effective_date = worker_first_dates[worker_id]
                                
                                wage_rate = WageRate(
                                    worker_id=worker_id, 
                                    agency=agency, 
                                    base_rate=base_rate, 
                                    role=position, 
                                    markup=markup, 
                                    effective_date=effective_date
                                )
                                db.session.add(wage_rate)
                                wage_rates_created += 1
                            except ValueError as e:
                                flash(f'Warning: Could not set wage rate for {worker_id}: {str(e)}', 'warning')
                db.session.commit()
                # Also update in-memory DataFrame for analytics
                df['worker_id'] = df['worker_id'].astype(str).str.strip()
                current_app.config['TIMESHEET_DF'] = df
                
                # Success message with wage rates info
                if wage_rates_created > 0:
                    flash(f'Successfully uploaded {timesheet_file.filename} with {inserted} new entries and created {wage_rates_created} wage rates', 'success')
                else:
                    flash(f'Successfully uploaded {timesheet_file.filename} with {inserted} new entries', 'success')
                did_upload = True
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
            # Create empty chart_data for template
            chart_data = {
                'current_week': datetime.today().isocalendar()[1],
                'previous_week': datetime.today().isocalendar()[1] - 1,
                'current_regular': 0,
                'current_overtime': 0,
                'previous_regular': 0,
                'previous_overtime': 0
            }
            return render_template('dashboard.html', summary=None, predictions=None, worker_filter='', week_filter='', show_all=show_all, is_forecast=True, chart_data=chart_data)
        df = pd.DataFrame([
            {
                'worker_id': e.worker_id,
                'date': e.date,
                'time_in': e.time_in,
                'time_out': e.time_out,
                'lunch_minutes': e.lunch_minutes,
                'agency': e.agency
            }
            for e in entries
        ])
        current_app.config['TIMESHEET_DF'] = df
    
    # Process timesheet data to get summary for chart_data
    processed_df, summary = process_timesheet(df.copy())
    
    # Get current week for chart data (use same logic as dashboard route)
    current_week = datetime.today().isocalendar()[1]
    current_week_data = summary[summary['week'] == current_week]
    
    # Prepare chart data similar to dashboard route
    chart_data = prepare_weekly_chart_data(current_week_data, '')
    
    # Generate predictions
    predictions = forecast_labor_needs(processed_df)
    if not show_all:
        active_workers = {w.worker_id for w in Worker.query.filter_by(is_active=True).all()}
        predictions = predictions[predictions['worker_id'].isin(active_workers)]
    
    return render_template('dashboard.html', summary=None, predictions=predictions, worker_filter='', week_filter='', show_all=show_all, is_forecast=True, chart_data=chart_data)

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