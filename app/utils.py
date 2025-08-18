import pandas as pd
from datetime import datetime, timedelta, date
from sklearn.linear_model import LinearRegression

import numpy as np

from flask import current_app
from . import db
from .models import Worker, WageRate, Agency, AgencyMarkup
from .validation import get_base_rate_for_position, normalize_position

def round_time(dt, round_to=15):
    """Round a datetime object to the nearest 'round_to' minutes."""
    seconds = (dt - dt.replace(hour=0, minute=0, second=0, microsecond=0)).seconds
    rounding = (seconds + round_to * 60 / 2) // (round_to * 60) * (round_to * 60)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(seconds=rounding)

def calculate_daily_hours(row, rounding_interval=None):
    """Calculate daily work hours minus lunch break."""
    time_in = row['time_in']
    time_out = row['time_out']
    duration = (time_out - time_in).total_seconds() / 3600.0
    lunch = row.get('lunch_minutes', 30) / 60.0
    daily_hours = duration - lunch
    return max(0, daily_hours)

def process_timesheet(df, rounding_interval=None):
    # Convert 'date' to a date object (if not already)
    df['date'] = pd.to_datetime(df['date']).dt.date

    def convert_time(value, date_val):
        # If the value is already a Timestamp, return it; otherwise, combine with date_val.
        import datetime
        if isinstance(value, pd.Timestamp):
            return value
        elif isinstance(value, datetime.time):
            # Already a time object, combine with date
            return datetime.datetime.combine(date_val, value)
        else:
            # Combine the date (converted to string) with the time string.
            return pd.to_datetime(str(date_val) + ' ' + str(value))

    # Replace the conversion lines with lambdas that call convert_time
    df['time_in'] = df.apply(lambda row: convert_time(row['time_in'], row['date']), axis=1)
    df['time_out'] = df.apply(lambda row: convert_time(row['time_out'], row['date']), axis=1)
    
    # Handle overnight shifts: if time_out < time_in, add one day
    df['time_out'] = df.apply(
        lambda row: row['time_out'] + timedelta(days=1)
        if row['time_out'] < row['time_in'] else row['time_out'], axis=1)
    
    # Calculate daily hours using the helper function (which subtracts lunch)
    df['daily_hours'] = df.apply(lambda row: calculate_daily_hours(row), axis=1)
    
    # Assign a week number (using ISO week from the original date)
    df['week'] = df['date'].apply(lambda d: datetime.combine(d, datetime.min.time()).isocalendar()[1])
    
    # Group by worker and week to compute weekly hours, aggregating agency as a comma-separated string
    summary = df.groupby(['worker_id', 'week']).agg(
        total_hours=('daily_hours', 'sum'),
        agencies_worked=('agency', lambda x: ', '.join(sorted(set(str(a) for a in x if pd.notnull(a)))))
    ).reset_index()
    summary['remaining_hours'] = 40 - summary['total_hours']
    
    def alert_status(hours):
        if hours >= 40:
            return 'Overtime'
        elif hours >= 35:
            return 'Approaching overtime'
        else:
            return ''

    summary['alert'] = summary['total_hours'].apply(alert_status)
    
    return df, summary

def update_entry(df, index, **kwargs):
    """Update a specific timesheet row."""
    for key, value in kwargs.items():
        if key in df.columns:
            if key == 'date':
                df.at[index, key] = pd.to_datetime(value).date()
            elif key in ['time_in', 'time_out']:
                # Use existing date to combine with new time
                date = df.at[index, 'date']
                df.at[index, key] = pd.to_datetime(str(date) + ' ' + value)
            else:
                df.at[index, key] = value
    return df

def calculate_agency_hours(df, rounding_interval=None):
    """
    Calculate total regular and overtime hours worked by each agency, grouped by month.
    The dataset must include an 'agency' column.
    Regular hours are capped at 40 hours per week per worker; overtime is any hour above 40 in a week.
    """
    processed_df, _ = process_timesheet(df, rounding_interval)
    if 'agency' not in processed_df.columns:
        raise ValueError("The dataset does not include the 'agency' column.")
    
    # Create a month column in the format YYYY-MM based on the date
    processed_df['month'] = pd.to_datetime(processed_df['date']).dt.strftime('%Y-%m')
    
    # Group by worker_id, week, agency, and month to calculate weekly total hours for each worker
    weekly_summary = processed_df.groupby(['worker_id', 'week', 'agency', 'month']).agg(
        weekly_total_hours=('daily_hours', 'sum')
    ).reset_index()
    
    # Calculate regular hours and overtime hours for each weekly summary
    weekly_summary['regular_hours'] = weekly_summary['weekly_total_hours'].apply(lambda x: min(x, 40))
    weekly_summary['overtime_hours'] = weekly_summary['weekly_total_hours'].apply(lambda x: max(x - 40, 0))
    
    # Now group by agency and month to get total regular and overtime hours
    agency_summary = weekly_summary.groupby(['agency', 'month']).agg(
        total_regular_hours=('regular_hours', 'sum'),
        total_overtime_hours=('overtime_hours', 'sum')
    ).reset_index()
    # Add total_hours column
    agency_summary['total_hours'] = agency_summary['total_regular_hours'] + agency_summary['total_overtime_hours']
    return agency_summary

def forecast_labor_needs(df):
    """
    Forecast next week's total hours per worker and flag potential overtime using Linear regression.
    Returns a DataFrame with columns: worker_id, predicted_hours, overtime_risk.
    """
    # Prepare timesheet data
    df['date'] = pd.to_datetime(df['date'])
    df['week'] = df['date'].dt.isocalendar().week
    df['year'] = df['date'].dt.isocalendar().year
    weekly = df.groupby(['worker_id', 'year', 'week']).agg(total_hours=('daily_hours', 'sum')).reset_index()
    
    results = []
    for worker_id, group in weekly.groupby('worker_id'):
        group = group.sort_values(['year', 'week'])
        group = group.reset_index(drop=True)
        group['week_idx'] = np.arange(len(group))
        X = group[['week_idx']].values
        y = group['total_hours'].values
        if len(group) < 2:
            pred_hours = y[-1] if len(y) > 0 else 0
        else:
            model = LinearRegression()
            model.fit(X, y)
            # Predict for next week
            next_week_idx = len(group)
            pred_hours = model.predict([[next_week_idx]])[0]
        overtime_risk = pred_hours >= 40
        results.append({
            'worker_id': worker_id,
            'predicted_hours': round(pred_hours, 2),
            'overtime_risk': overtime_risk
        })
    return pd.DataFrame(results)


def get_agency_markup_for_date(agency_name, effective_date=None):
    """
    Get the markup rate for an agency on a specific date.
    Returns the most recent markup effective on or before the given date.
    
    Args:
        agency_name (str): Name of the staffing agency
        effective_date (date, optional): Date to check markup for. Defaults to today.
    
    Returns:
        float: Markup rate (e.g., 0.25 for 25%) or 0.0 if no markup found
    """
    if effective_date is None:
        effective_date = date.today()
    
    # Find the agency
    agency = Agency.query.filter_by(name=agency_name).first()
    if not agency:
        current_app.logger.warning(f"Agency '{agency_name}' not found in database")
        return 0.0
    
    # Get the most recent markup effective on or before the given date
    markup_obj = AgencyMarkup.query.filter(
        AgencyMarkup.agency_id == agency.id,
        AgencyMarkup.effective_date <= effective_date
    ).order_by(AgencyMarkup.effective_date.desc()).first()
    
    if markup_obj:
        return markup_obj.markup
    else:
        current_app.logger.warning(f"No markup found for agency '{agency_name}' on date {effective_date}")
        return 0.0


def calculate_wage_rate(position, agency_name, effective_date=None):
    """
    Calculate the total wage rate for a worker based on position and agency.
    
    Args:
        position (str): Worker position ('general labor' or 'forklift driver')
        agency_name (str): Staffing agency name
        effective_date (date, optional): Date to calculate rate for. Defaults to today.
    
    Returns:
        tuple: (base_rate, markup_rate, total_rate)
    """
    if effective_date is None:
        effective_date = date.today()
    
    # Normalize position and get base rate
    normalized_position = normalize_position(position)
    base_rate = get_base_rate_for_position(normalized_position)
    
    # Get agency markup
    markup = get_agency_markup_for_date(agency_name, effective_date)
    
    # Calculate total rate
    total_rate = base_rate * (1 + markup)
    
    return base_rate, markup, total_rate


def get_worker_hire_date(worker_id):
    """Get worker's hire date from first timesheet entry."""
    from .models import TimesheetEntry
    first_entry = TimesheetEntry.query.filter_by(
        worker_id=worker_id
    ).order_by(TimesheetEntry.date.asc()).first()
    
    return first_entry.date if first_entry else date.today()


def get_worker_current_agency(worker_id):
    """Get worker's most recent agency from timesheet data (for agency transfers)."""
    from .models import TimesheetEntry
    # Get the most recent timesheet entry for this worker
    recent_entry = TimesheetEntry.query.filter(
        TimesheetEntry.worker_id == worker_id,
        TimesheetEntry.agency.isnot(None)
    ).order_by(TimesheetEntry.date.desc()).first()
    
    if recent_entry:
        return recent_entry.agency
    
    # Fallback to existing wage rate agency
    existing_wage = WageRate.query.filter(
        WageRate.worker_id == worker_id,
        WageRate.agency.isnot(None)
    ).first()
    
    return existing_wage.agency if existing_wage else None


def ensure_worker_wage_rate(worker_id, position, agency_name, effective_date=None, base_rate_override=None):
    """
    Ensure a worker has a proper wage rate entry in the database.
    Creates or updates the wage rate based on position and agency.
    Supports manual base rate overrides for pay raises.
    
    Business Rules:
    1. Effective date = worker's first appearance (hire date)
    2. Agency = worker's most recent agency (for transfers)
    3. Base rate can be manually overridden (for pay raises)
    4. One wage rate entry per worker (updates for agency transfers)
    
    Args:
        worker_id (str): Worker ID (corresponds to worker's name)
        position (str): Worker position ('general labor' or 'forklift driver')
        agency_name (str): Staffing agency name (current agency)
        effective_date (date, optional): IGNORED - always uses hire date
        base_rate_override (float, optional): Manual override for base rate (for pay raises)
    
    Returns:
        WageRate: The created or updated WageRate object
    """
    # BUSINESS RULE: Effective date is ALWAYS the worker's hire date
    hire_date = get_worker_hire_date(worker_id)
    
    # Use current agency if not specified (for agency transfers)
    if not agency_name:
        agency_name = get_worker_current_agency(worker_id)
        if not agency_name:
            raise ValueError(f"Cannot determine agency for worker {worker_id}")
    
    # Normalize position
    normalized_position = normalize_position(position)
    
    # Calculate base rate (with override support)
    if base_rate_override is not None:
        base_rate = base_rate_override
        current_app.logger.info(f"Using manual base rate override for {worker_id}: ${base_rate:.2f}")
    else:
        base_rate = get_base_rate_for_position(normalized_position)
    
    # Get agency markup for current rates (use today's date)
    markup = get_agency_markup_for_date(agency_name, date.today())
    
    # Check if worker exists in Worker table
    worker = Worker.query.filter_by(worker_id=worker_id).first()
    if not worker:
        # Create worker if not exists
        worker = Worker(worker_id=worker_id, name=None, is_active=True)
        db.session.add(worker)
        current_app.logger.info(f"Created new worker: {worker_id}")
    
    # BUSINESS RULE: One wage rate per worker (check by worker_id only)
    existing_wage = WageRate.query.filter_by(worker_id=worker_id).first()
    
    if existing_wage:
        # Update existing wage rate
        
        # Detect manual override
        has_manual_override = False
        if existing_wage.base_rate is not None and existing_wage.role:
            standard_rate = get_base_rate_for_position(existing_wage.role)
            if abs(existing_wage.base_rate - standard_rate) > 0.01:
                has_manual_override = True
                current_app.logger.info(f"Preserving manual override for {worker_id}: ${existing_wage.base_rate:.2f}")
        
        # Update fields
        existing_wage.role = normalized_position
        existing_wage.agency = agency_name  # Update for agency transfers
        existing_wage.markup = markup  # Update markup for new agency
        existing_wage.effective_date = hire_date  # Always use hire date
        
        # Only update base rate if override is specified or no manual override exists
        if base_rate_override is not None:
            existing_wage.base_rate = base_rate
        elif not has_manual_override:
            existing_wage.base_rate = base_rate
        
        current_app.logger.info(f"Updated wage rate for worker {worker_id} (agency: {agency_name})")
        db.session.commit()
        return existing_wage
    else:
        # Create new wage rate
        new_wage = WageRate(
            worker_id=worker_id,
            base_rate=base_rate,
            role=normalized_position,
            agency=agency_name,
            markup=markup,
            effective_date=hire_date  # Always use hire date
        )
        db.session.add(new_wage)
        total_rate = base_rate * (1 + markup)
        current_app.logger.info(f"Created wage rate for worker {worker_id}: ${total_rate:.2f}/hr (${base_rate:.2f} + {markup:.1%})")
        db.session.commit()
        return new_wage


def populate_missing_wage_rates(timesheet_df=None):
    """
    Find workers missing wage rates and populate them based on timesheet data.
    
    Args:
        timesheet_df (DataFrame, optional): Timesheet data with worker_id, position, agency columns.
                                           If None, will attempt to get from current_app.config.
    
    Returns:
        dict: Summary of actions taken
    """
    if timesheet_df is None:
        timesheet_df = current_app.config.get('MASTER_TIMESHEET_DF')
        if timesheet_df is None or timesheet_df.empty:
            return {"error": "No timesheet data available"}
    
    summary = {
        "workers_processed": 0,
        "wage_rates_created": 0,
        "wage_rates_updated": 0,
        "errors": []
    }
    
    # Get worker information following business rules
    if 'position' in timesheet_df.columns and 'agency' in timesheet_df.columns:
        # Group by worker to get hire date and current agency
        worker_info = timesheet_df.groupby('worker_id').agg({
            'position': 'first',  # Take first occurrence for position
            'agency': 'last',     # Take MOST RECENT agency (for transfers)
            'date': ['min', 'max']  # Get both hire date (min) and latest date (max)
        }).reset_index()
        
        # Flatten column names
        worker_info.columns = ['worker_id', 'position', 'current_agency', 'hire_date', 'latest_date']
    else:
        return {"error": "Timesheet data missing required columns: position, agency"}
    
    for _, row in worker_info.iterrows():
        try:
            worker_id = row['worker_id']
            position = row['position']
            current_agency = row['current_agency']  # Most recent agency
            hire_date = pd.to_datetime(row['hire_date']).date() if pd.notnull(row['hire_date']) else date.today()
            
            summary["workers_processed"] += 1
            
            # Check if worker has any wage rate
            existing_wage = WageRate.query.filter_by(worker_id=worker_id).first()
            
            if existing_wage:
                # Check if update is needed (agency transfer, wrong hire date, etc.)
                needs_update = False
                
                # Check for agency transfer
                if existing_wage.agency != current_agency:
                    needs_update = True
                
                # Check if effective date is wrong (should be hire date)
                if existing_wage.effective_date != hire_date:
                    needs_update = True
                
                # Check for missing data
                if not existing_wage.role or existing_wage.base_rate is None or existing_wage.markup is None:
                    needs_update = True
                
                if needs_update:
                    ensure_worker_wage_rate(worker_id, position, current_agency)
                    summary["wage_rates_updated"] += 1
            else:
                # Create new wage rate
                ensure_worker_wage_rate(worker_id, position, current_agency)
                summary["wage_rates_created"] += 1
                
        except Exception as e:
            error_msg = f"Error processing worker {worker_id}: {str(e)}"
            summary["errors"].append(error_msg)
            current_app.logger.error(error_msg)
    
    return summary


def update_all_worker_wage_rates(dry_run=False):
    """
    Update wage rates for all workers based on current timesheet data.
    This function ensures all workers have accurate wage rates.
    
    Args:
        dry_run (bool): If True, only return what would be changed without making changes
    
    Returns:
        dict: Summary of changes made or that would be made
    """
    timesheet_df = current_app.config.get('MASTER_TIMESHEET_DF')
    if timesheet_df is None or timesheet_df.empty:
        return {"error": "No timesheet data available"}
    
    if dry_run:
        current_app.logger.info("Running wage rate update in DRY RUN mode")
    
    summary = populate_missing_wage_rates(timesheet_df)
    
    if not dry_run:
        db.session.commit()
        current_app.logger.info(f"Wage rate update completed: {summary}")
    else:
        db.session.rollback()
        current_app.logger.info(f"DRY RUN completed: {summary}")
    
    return summary


def add_new_worker_with_wage_rate(worker_id, position, agency_name, name=None, effective_date=None, base_rate_override=None):
    """
    Add a new worker to the system with appropriate wage rate.
    This is a convenience function for adding workers programmatically.
    Supports manual base rate overrides for special pay arrangements.
    
    Args:
        worker_id (str): Unique worker identifier (worker's name)
        position (str): Worker position ('general labor' or 'forklift driver')
        agency_name (str): Staffing agency name
        name (str, optional): Worker's full name (if different from worker_id)
        effective_date (date, optional): Effective date for wage rate. Defaults to today.
        base_rate_override (float, optional): Manual override for base rate (for special pay)
    
    Returns:
        dict: Status with worker and wage_rate objects
    """
    if effective_date is None:
        effective_date = date.today()
    
    try:
        # Check if worker already exists
        existing_worker = Worker.query.filter_by(worker_id=worker_id).first()
        if existing_worker:
            current_app.logger.warning(f"Worker {worker_id} already exists")
            # Still ensure wage rate is correct
            wage_rate = ensure_worker_wage_rate(worker_id, position, agency_name, effective_date, base_rate_override)
            total_rate = wage_rate.base_rate * (1 + wage_rate.markup)
            return {
                'status': 'updated',
                'worker': existing_worker,
                'wage_rate': wage_rate,
                'message': f'Worker {worker_id} already existed, wage rate updated to ${total_rate:.2f}/hr'
            }
        
        # Create new worker
        worker = Worker(worker_id=worker_id, name=name or worker_id, is_active=True)
        db.session.add(worker)
        
        # Create wage rate
        wage_rate = ensure_worker_wage_rate(worker_id, position, agency_name, effective_date, base_rate_override)
        
        db.session.commit()
        
        # Calculate total rate for message
        total_rate = wage_rate.base_rate * (1 + wage_rate.markup)
        
        override_note = f" (override: ${base_rate_override:.2f})" if base_rate_override else ""
        current_app.logger.info(f"Added new worker {worker_id} with wage rate ${total_rate:.2f}/hr{override_note}")
        
        return {
            'status': 'created',
            'worker': worker,
            'wage_rate': wage_rate,
            'message': f'Worker {worker_id} created with wage rate ${total_rate:.2f}/hr{override_note}'
        }
        
    except Exception as e:
        db.session.rollback()
        error_msg = f"Error adding worker {worker_id}: {str(e)}"
        current_app.logger.error(error_msg)
        raise ValueError(error_msg)