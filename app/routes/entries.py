from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from ..utils import process_timesheet, update_entry

entries_bp = Blueprint('entries', __name__)

@entries_bp.route('/entries')
def view_entries():
    # Retrieve the master DataFrame
    df = current_app.config.get('TIMESHEET_DF')
    if df is None or df.empty:
        flash("No timesheet data available.")
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

    return render_template('entries.html',
                           df_filtered=df_filtered,
                           worker_id=worker_id,
                           week=week)

@entries_bp.route('/update/<int:index>', methods=['GET', 'POST'])
def update_entry_route(index):
    # Retrieve the master DataFrame
    df = current_app.config.get('TIMESHEET_DF')
    if df is None or df.empty:
        flash("No timesheet data available.")
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        # Read form inputs
        worker_id = request.form.get('worker_id')
        date_val = request.form.get('date')
        time_in_val = request.form.get('time_in')
        time_out_val = request.form.get('time_out')
        lunch_str = request.form.get('lunch_minutes', '').strip()
        lunch_minutes = int(lunch_str) if lunch_str != '' else 30

        try:
            updated_df = update_entry(
                df.copy(), index,
                worker_id=worker_id,
                date=date_val,
                time_in=time_in_val,
                time_out=time_out_val,
                lunch_minutes=lunch_minutes
            )
            current_app.config['TIMESHEET_DF'] = updated_df
            flash("Entry updated successfully.")
            # Redirect back to dashboard with filters
            return redirect(url_for('dashboard.dashboard', worker=worker_id, week=request.form.get('week', '')))
        except Exception as e:
            flash(f"Error updating entry: {e}")
            return redirect(url_for('entries.update_entry_route', index=index))

    # GET request: show form
    processed_df, _ = process_timesheet(df.copy())
    try:
        entry = processed_df.iloc[index]
    except Exception:
        flash("Invalid entry index.")
        return redirect(url_for('dashboard.dashboard'))

    return render_template('update_entry.html', index=index, entry=entry)