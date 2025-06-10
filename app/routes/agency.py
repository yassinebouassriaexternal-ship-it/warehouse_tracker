from flask import Blueprint, render_template, flash, redirect, url_for, current_app
from ..utils import calculate_agency_hours, process_timesheet
from ..models import WageRate
import numpy as np
import pandas as pd
from datetime import datetime

agency_bp = Blueprint('agency_summary', __name__)

def calculate_weekly_trends(df):
    """Calculate weekly total hours by agency for trending analysis."""
    if df is None or df.empty:
        return {}, []
    
    # Ensure we have the daily_hours column
    if 'daily_hours' not in df.columns:
        df, _ = process_timesheet(df.copy())
    
    # Convert date to datetime if not already
    df['date'] = pd.to_datetime(df['date'])
    
    # Add week information
    df['year'] = df['date'].dt.year
    df['week'] = df['date'].dt.isocalendar().week
    df['week_start'] = df['date'].dt.to_period('W').dt.start_time.dt.date
    
    # Group by agency and week to get total hours
    weekly_summary = df.groupby(['Agency', 'year', 'week', 'week_start']).agg(
        total_hours=('daily_hours', 'sum')
    ).reset_index()
    
    # Create week labels (e.g., "2023-W25")
    weekly_summary['week_label'] = weekly_summary['year'].astype(str) + '-W' + weekly_summary['week'].astype(str).str.zfill(2)
    
    # Sort by week_start
    weekly_summary = weekly_summary.sort_values('week_start')
    
    # Get unique agencies and weeks
    agencies = sorted(weekly_summary['Agency'].unique().tolist())
    weeks = weekly_summary['week_label'].unique().tolist()
    
    # Build agency weekly data dict
    agency_weekly_hours = {}
    for agency in agencies:
        agency_data = weekly_summary[weekly_summary['Agency'] == agency]
        hours_by_week = []
        for week in weeks:
            week_data = agency_data[agency_data['week_label'] == week]
            if not week_data.empty:
                hours_by_week.append(float(week_data['total_hours'].values[0]))
            else:
                hours_by_week.append(0)
        agency_weekly_hours[agency] = hours_by_week
    
    return agency_weekly_hours, weeks

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
        
        # Calculate weekly trends for the trending chart
        agency_weekly_hours, weeks = calculate_weekly_trends(df.copy())
        # --- Cost Calculation ---
        # Add cost columns to summary
        summary['total_cost'] = 0.0
        for i, row in summary.iterrows():
            agency = row['Agency']
            month = row['month']
            # Get all entries for this agency/month
            month_entries = df[(df['Agency'] == agency) & (pd.to_datetime(df['date']).dt.strftime('%Y-%m') == month)]
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
                    if role == 'forklift':
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
        # Prepare data for chart
        agencies = summary['Agency'].unique().tolist()
        months = sorted(summary['month'].unique().tolist())
        # Build a dict: {agency: [cost_per_month]}
        agency_costs = {}
        for agency in agencies:
            costs = []
            for month in months:
                row = summary[(summary['Agency'] == agency) & (summary['month'] == month)]
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
                row = summary[(summary['Agency'] == agency) & (summary['month'] == month)]
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
        agencies=agencies,
        months=months,
        agency_costs=agency_costs,
        regular_hours=regular_hours,
        overtime_hours=overtime_hours,
        agency_weekly_hours=agency_weekly_hours,
        weeks=weeks
    )