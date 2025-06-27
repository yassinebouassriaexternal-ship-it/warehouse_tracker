from flask import Blueprint, render_template, flash, redirect, url_for, current_app
from ..utils import calculate_agency_hours, process_timesheet
from ..models import WageRate
import numpy as np
import pandas as pd
from datetime import datetime

agency_bp = Blueprint('agency_summary', __name__)



@agency_bp.route('/agency_summary')
def agency_summary():
    # Read the master timesheet DataFrame from app config
    df = current_app.config.get('TIMESHEET_DF')
    if df is None or df.empty:
        flash("No timesheet data available.")
        return redirect(url_for('dashboard.dashboard'))
    # Ensure daily_hours column exists
    if 'daily_hours' not in df.columns:
        df, _ = process_timesheet(df.copy())
    try:
        summary = calculate_agency_hours(df.copy())
        # --- Cost Calculation ---
        # Add cost columns to summary
        summary['total_cost'] = 0.0
        for i, row in summary.iterrows():
            agency = row['agency']
            month = row['month']
            # Get all entries for this agency/month
            month_entries = df[(df['agency'] == agency) & (pd.to_datetime(df['date']).dt.strftime('%Y-%m') == month)]
            total_cost = 0.0
            for _, entry in month_entries.iterrows():
                worker_id = entry['worker_id']
                entry_date = pd.to_datetime(entry['date']).date()
                # Find the most recent WageRate effective on or before entry_date
                wage = WageRate.query.filter(
                    WageRate.worker_id == worker_id,
                    WageRate.effective_date <= entry_date
                ).order_by(WageRate.effective_date.desc()).first()
                if wage:
                    base_rate = wage.base_rate
                    markup = wage.markup if wage.markup is not None else (0.25 if wage.agency == 'JJ' else 0.30 if wage.agency == 'Stride' else 0.0)
                else:
                    role = entry['role'] if 'role' in entry and pd.notnull(entry['role']) else None
                    if role == 'forklift driver':
                        base_rate = 18.0
                    else:
                        base_rate = 16.0
                    markup = 0.25 if agency == 'JJ' else 0.30 if agency == 'Stride' else 0.0
                # Calculate cost for this entry
                hours = entry['daily_hours']
                cost = hours * base_rate * (1 + markup)
                total_cost += cost
            summary.at[i, 'total_cost'] = total_cost
        # --- End cost calculation ---
        
        # --- Calculate totals across all agencies per month ---
        monthly_totals = summary.groupby('month').agg({
            'total_regular_hours': 'sum',
            'total_overtime_hours': 'sum',
            'total_hours': 'sum',
            'total_cost': 'sum'
        }).reset_index()
        monthly_totals = monthly_totals.sort_values('month')
        # --- End totals calculation ---
        
        # Prepare data for chart
        agencies = summary['agency'].unique().tolist()
        months = sorted(summary['month'].unique().tolist())
        # Build a dict: {agency: [cost_per_month]}
        agency_costs = {}
        for agency in agencies:
            costs = []
            for month in months:
                row = summary[(summary['agency'] == agency) & (summary['month'] == month)]
                if not row.empty:
                    costs.append(float(row['total_cost'].values[0]))
                else:
                    costs.append(0)
            agency_costs[agency] = costs
            
        # Extract regular and overtime hours data for chart
        regular_hours = {}
        overtime_hours = {}
        for agency in agencies:
            reg_hours = []
            ovt_hours = []
            for month in months:
                row = summary[(summary['agency'] == agency) & (summary['month'] == month)]
                if not row.empty:
                    reg_hours.append(float(row['total_regular_hours'].values[0]))
                    ovt_hours.append(float(row['total_overtime_hours'].values[0]))
                else:
                    reg_hours.append(0)
                    ovt_hours.append(0)
            regular_hours[agency] = reg_hours
            overtime_hours[agency] = ovt_hours
    except Exception as e:
        flash(str(e))
        return redirect(url_for('dashboard.dashboard'))
    return render_template(
        'agency_summary.html',
        summary=summary,
        monthly_totals=monthly_totals,
        agencies=agencies,
        months=months,
        agency_costs=agency_costs,
        regular_hours=regular_hours,
        overtime_hours=overtime_hours
    )