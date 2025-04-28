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
        # Prepare data for chart
        agencies = summary['Agency'].unique().tolist()
        months = sorted(summary['month'].unique().tolist())

        # Build a dict: {agency: [hours_per_month]}
        agency_hours = {}
        for agency in agencies:
            hours = []
            for month in months:
                row = summary[(summary['Agency'] == agency) & (summary['month'] == month)]
                if not row.empty:
                    hours.append(float(row['total_regular_hours'].values[0]) + float(row['total_overtime_hours'].values[0]))
                else:
                    hours.append(0)
            agency_hours[agency] = hours
    except Exception as e:
        flash(str(e))
        return redirect(url_for('dashboard.dashboard'))
    return render_template(
        'agency_summary.html',
        summary=summary,
        agencies=agencies,
        months=months,
        agency_hours=agency_hours
    )