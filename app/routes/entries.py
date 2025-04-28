from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from ..utils import process_timesheet, update_entry
from ..validation import (
    validate_time_format, validate_date_format, validate_lunch_minutes,
    validate_worker_id, validate_agency, calculate_shift_duration
)
import pandas as pd
from datetime import datetime

entries_bp = Blueprint('entries', __name__)

@entries_bp.route('/entries')
def view_entries():
    # Retrieve the master DataFrame
    df = current_app.config.get('TIMESHEET_DF')
    if df is None or df.empty:
        flash("No timesheet data available.", 'error')
        return redirect(url_for('dashboard.dashboard'))

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

    return render_template('entries.html',
                           df_filtered=df_filtered,
                           worker_id=worker_id,
                           week=week,
                           weeks=weeks,
                           hours=hours)

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