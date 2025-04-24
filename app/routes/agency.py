from flask import Blueprint, render_template, flash, redirect, url_for, current_app
from ..utils import calculate_agency_hours

agency_bp = Blueprint('agency_summary', __name__)

@agency_bp.route('/agency_summary')
def agency_summary():
    # Read the master timesheet DataFrame from app config
    df = current_app.config.get('TIMESHEET_DF')
    if df is None or df.empty:
        flash("No timesheet data available.")
        return redirect(url_for('dashboard.dashboard'))
    try:
        summary = calculate_agency_hours(df.copy())
    except Exception as e:
        flash(str(e))
        return redirect(url_for('dashboard.dashboard'))
    return render_template('agency_summary.html', summary=summary)