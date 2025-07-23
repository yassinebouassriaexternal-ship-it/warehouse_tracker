from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from ..utils import calculate_agency_hours, process_timesheet
from ..models import WageRate, Agency, AgencyMarkup
from .. import db
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
                else:
                    role = entry['role'] if 'role' in entry and pd.notnull(entry['role']) else None
                    if role == 'forklift driver':
                        base_rate = 18.0
                    else:
                        base_rate = 16.0
                # --- Get correct agency markup ---
                agency_obj = Agency.query.filter_by(name=agency).first()
                markup = 0.0
                if agency_obj:
                    markup_obj = AgencyMarkup.query.filter(
                        AgencyMarkup.agency_id == agency_obj.id,
                        AgencyMarkup.effective_date <= entry_date
                    ).order_by(AgencyMarkup.effective_date.desc()).first()
                    if markup_obj:
                        markup = markup_obj.markup
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

@agency_bp.route('/manage_agencies', methods=['GET', 'POST'])
def manage_agencies():
    agencies = Agency.query.order_by(Agency.name).all()
    selected_agency = None
    markups = []
    agency_id = request.args.get('agency_id', type=int)
    if agency_id:
        selected_agency = Agency.query.get(agency_id)
        if selected_agency:
            markups = AgencyMarkup.query.filter_by(agency_id=selected_agency.id).order_by(AgencyMarkup.effective_date.desc()).all()
    if request.method == 'POST':
        # Add new markup
        agency_id = request.form.get('agency_id', type=int)
        markup = request.form.get('markup', type=float)
        effective_date = request.form.get('effective_date')
        if agency_id and markup is not None and effective_date:
            try:
                effective_date = pd.to_datetime(effective_date).date()
                new_markup = AgencyMarkup(agency_id=agency_id, markup=markup, effective_date=effective_date)
                db.session.add(new_markup)
                db.session.commit()
                flash('Markup added successfully.', 'success')
                return redirect(url_for('agency_summary.manage_agencies', agency_id=agency_id))
            except Exception as e:
                db.session.rollback()
                flash(f'Error adding markup: {e}', 'error')
    return render_template('manage_agencies.html', agencies=agencies, selected_agency=selected_agency, markups=markups)

@agency_bp.route('/edit_agency_markup/<int:markup_id>', methods=['GET', 'POST'])
def edit_agency_markup(markup_id):
    markup = AgencyMarkup.query.get_or_404(markup_id)
    if request.method == 'POST':
        try:
            markup.markup = float(request.form.get('markup'))
            markup.effective_date = pd.to_datetime(request.form.get('effective_date')).date()
            db.session.commit()
            flash('Markup updated successfully.', 'success')
            return redirect(url_for('agency_summary.manage_agencies', agency_id=markup.agency_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating markup: {e}', 'error')
    return render_template('edit_agency_markup.html', markup=markup)

@agency_bp.route('/delete_agency_markup/<int:markup_id>', methods=['POST'])
def delete_agency_markup(markup_id):
    markup = AgencyMarkup.query.get_or_404(markup_id)
    agency_id = markup.agency_id
    try:
        db.session.delete(markup)
        db.session.commit()
        flash('Markup deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting markup: {e}', 'error')
    return redirect(url_for('agency_summary.manage_agencies', agency_id=agency_id))
