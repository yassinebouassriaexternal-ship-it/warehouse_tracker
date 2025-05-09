from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from ..utils import process_timesheet, update_entry
from ..validation import (
    validate_time_format, validate_date_format, validate_lunch_minutes,
    validate_worker_id, validate_agency, calculate_shift_duration
)
import pandas as pd
from datetime import datetime
from ..models import TimesheetEntry

entries_bp = Blueprint('entries', __name__)

@entries_bp.route('/entries')
def view_entries():
    # Retrieve the master DataFrame
    df = current_app.config.get('TIMESHEET_DF')
    if df is None or df.empty:
        # Load from database if not in memory
        entries = TimesheetEntry.query.all()
        if not entries:
            flash("No timesheet data available.", 'error')
            return redirect(url_for('dashboard.dashboard'))
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

    # Get filters
    worker_id = request.args.get('worker_id', '')
    week = request.args.get('week', '')

    # Process and filter
    processed_df, _ = process_timesheet(df.copy())
    df_filtered = processed_df.copy()
    if worker_id:
        df_filtered = df_filtered[df_filtered['worker_id'] == worker_id]
    if week:
        try:
            week_int = int(week)
            df_filtered = df_filtered[df_filtered['week'] == week_int]
        except ValueError:
            pass

    # Calculate weekly hours for this worker
    weekly_hours = (
        processed_df[processed_df['worker_id'] == worker_id]
        .groupby('week')['daily_hours']
        .sum()
        .reset_index()
        .sort_values('week')
    )
    # Convert to lists for chart.js
    weeks = weekly_hours['week'].tolist()
    hours = weekly_hours['daily_hours'].tolist()

    # --- Worker Analysis Metrics ---
    import calendar
    from datetime import date
    today = date.today()
    this_month = today.month
    this_year = today.year
    last_month = this_month - 1 if this_month > 1 else 12
    last_month_year = this_year if this_month > 1 else this_year - 1

    # Filter for this worker
    worker_df = processed_df[processed_df['worker_id'] == worker_id].copy()
    worker_df['month'] = pd.to_datetime(worker_df['date']).dt.month
    worker_df['year'] = pd.to_datetime(worker_df['date']).dt.year

    # Average hours per day for last month and this month
    avg_hours_this_month = worker_df[(worker_df['month'] == this_month) & (worker_df['year'] == this_year)]['daily_hours'].mean()
    avg_hours_last_month = worker_df[(worker_df['month'] == last_month) & (worker_df['year'] == last_month_year)]['daily_hours'].mean()

    # Morning vs afternoon shifts (before/after 12:00)
    morning_count = (worker_df['time_in'].dt.hour < 12).sum()
    afternoon_count = (worker_df['time_in'].dt.hour >= 12).sum()
    total_shifts = morning_count + afternoon_count
    morning_ratio = morning_count / total_shifts if total_shifts else 0
    afternoon_ratio = afternoon_count / total_shifts if total_shifts else 0

    # Additional metrics: total days worked, max hours in a day, min hours in a day
    total_days_worked = worker_df['date'].nunique()
    max_hours = worker_df['daily_hours'].max()
    min_hours = worker_df['daily_hours'].min()

    # Overtime Frequency: number of weeks with >40 hours
    overtime_weeks = (
        processed_df[processed_df['worker_id'] == worker_id]
        .groupby('week')['daily_hours']
        .sum()
        .gt(40)
        .sum()
    )

    # Longest Streak of Consecutive Workdays
    worker_dates_sorted = sorted(set(worker_df['date']))
    longest_streak = 0
    current_streak = 1 if worker_dates_sorted else 0
    for i in range(1, len(worker_dates_sorted)):
        if (worker_dates_sorted[i] - worker_dates_sorted[i-1]).days == 1:
            current_streak += 1
        else:
            if current_streak > longest_streak:
                longest_streak = current_streak
            current_streak = 1
    if current_streak > longest_streak:
        longest_streak = current_streak

    worker_metrics = {
        'avg_hours_this_month': avg_hours_this_month,
        'avg_hours_last_month': avg_hours_last_month,
        'morning_ratio': morning_ratio,
        'afternoon_ratio': afternoon_ratio,
        'total_days_worked': total_days_worked,
        'max_hours': max_hours,
        'min_hours': min_hours,
        'overtime_weeks': overtime_weeks,
        'longest_streak': longest_streak
    }

    return render_template('entries.html',
                           df_filtered=df_filtered,
                           worker_id=worker_id,
                           week=week,
                           weeks=weeks,
                           hours=hours,
                           worker_metrics=worker_metrics)

@entries_bp.route('/update/<int:index>', methods=['GET', 'POST'])
def update_entry_route(index):
    # Retrieve the master DataFrame
    df = current_app.config.get('TIMESHEET_DF')
    if df is None or df.empty:
        flash("No timesheet data available.", 'error')
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        try:
            # Validate form inputs
            worker_id = request.form.get('worker_id', '').strip()
            date_val = request.form.get('date', '').strip()
            time_in_val = request.form.get('time_in', '').strip()
            time_out_val = request.form.get('time_out', '').strip()
            lunch_str = request.form.get('lunch_minutes', '').strip()
            
            # Perform validation
            validate_worker_id(worker_id)
            validate_date_format(date_val)
            validate_time_format(time_in_val)
            validate_time_format(time_out_val)
            lunch_minutes = validate_lunch_minutes(lunch_str)
            
            # Validate time logic
            time_in = datetime.strptime(time_in_val, '%H:%M').time()
            time_out = datetime.strptime(time_out_val, '%H:%M').time()
            
            # Calculate and validate shift duration
            duration = calculate_shift_duration(time_in, time_out)
            if duration > 24:
                raise ValueError(f"Shift duration of {duration:.1f} hours is too long")
            if duration < 0.5:
                raise ValueError(f"Shift duration of {duration:.1f} hours is too short")

            # Update the entry
            updated_df = update_entry(
                df.copy(), index,
                worker_id=worker_id,
                date=date_val,
                time_in=time_in_val,
                time_out=time_out_val,
                lunch_minutes=lunch_minutes
            )
            
            current_app.config['TIMESHEET_DF'] = updated_df
            flash("Entry updated successfully.", 'success')
            return redirect(url_for('dashboard.dashboard', worker=worker_id, week=request.form.get('week', '')))
            
        except ValueError as e:
            flash(f"Validation error: {str(e)}", 'error')
            return redirect(url_for('entries.update_entry_route', index=index))
        except Exception as e:
            flash(f"Error updating entry: {str(e)}", 'error')
            return redirect(url_for('entries.update_entry_route', index=index))

    # GET request: show form
    processed_df, _ = process_timesheet(df.copy())
    try:
        entry = processed_df.iloc[index]
    except Exception:
        flash("Invalid entry index.", 'error')
        return redirect(url_for('dashboard.dashboard'))

    return render_template('update_entry.html', index=index, entry=entry)