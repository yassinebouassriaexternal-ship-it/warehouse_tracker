import pandas as pd
from datetime import datetime, timedelta

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
    
    # Group by worker and week to compute weekly hours
    summary = df.groupby(['worker_id', 'week']).agg(total_hours=('daily_hours', 'sum')).reset_index()
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
    The dataset must include an 'Agency' column.
    Regular hours are capped at 40 hours per week per worker; overtime is any hour above 40 in a week.
    """
    processed_df, _ = process_timesheet(df, rounding_interval)
    if 'Agency' not in processed_df.columns:
        raise ValueError("The dataset does not include the 'Agency' column.")
    
    # Create a month column in the format YYYY-MM based on the date
    processed_df['month'] = pd.to_datetime(processed_df['date']).dt.strftime('%Y-%m')
    
    # Group by worker_id, week, Agency, and month to calculate weekly total hours for each worker
    weekly_summary = processed_df.groupby(['worker_id', 'week', 'Agency', 'month']).agg(
        weekly_total_hours=('daily_hours', 'sum')
    ).reset_index()
    
    # Calculate regular hours and overtime hours for each weekly summary
    weekly_summary['regular_hours'] = weekly_summary['weekly_total_hours'].apply(lambda x: min(x, 40))
    weekly_summary['overtime_hours'] = weekly_summary['weekly_total_hours'].apply(lambda x: max(x - 40, 0))
    
    # Now group by Agency and month to get total regular and overtime hours
    agency_summary = weekly_summary.groupby(['Agency', 'month']).agg(
        total_regular_hours=('regular_hours', 'sum'),
        total_overtime_hours=('overtime_hours', 'sum')
    ).reset_index()
    # Add total_hours column
    agency_summary['total_hours'] = agency_summary['total_regular_hours'] + agency_summary['total_overtime_hours']
    return agency_summary