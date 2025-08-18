# Wage Rate Automation Documentation

This document explains the new automatic wage rate calculation and management system implemented in the warehouse tracker application.

## Overview

The system automatically calculates and assigns wage rates to workers based on:
- **Position**: General labor ($16/hr) or Forklift driver ($18/hr)
- **Staffing agency**: Markup percentages stored in the database
- **Effective dates**: Historical markup rates with date-based lookups

## Key Features

### 1. Automatic Wage Rate Calculation
- Base rates are determined by worker position
- Agency markups are retrieved from the database with effective date support
- Total wage rate = Base rate × (1 + Markup percentage)

### 2. Smart Data Integration
- New CSV uploads automatically create wage rates for workers
- Missing wage rates are identified and populated from timesheet data
- Existing workers get updated wage rates when position/agency changes

### 3. Database-Driven Markup Management
- Agency markups stored in `AgencyMarkup` table with effective dates
- Historical markup rates preserved for accurate cost calculations
- Replaces hardcoded markup values with flexible database approach

## New Functions Added

### Core Utility Functions (`app/utils.py`)

#### `get_agency_markup_for_date(agency_name, effective_date=None)`
Gets the correct markup rate for an agency on a specific date.
```python
markup = get_agency_markup_for_date('JJ Staffing', date(2024, 1, 1))
# Returns: 0.25 (for 25% markup)
```

#### `calculate_wage_rate(position, agency_name, effective_date=None)`
Calculates base rate, markup, and total wage rate.
```python
base_rate, markup, total_rate = calculate_wage_rate('forklift driver', 'JJ Staffing')
# Returns: (18.0, 0.25, 22.50)
```

#### `ensure_worker_wage_rate(worker_id, position, agency_name, effective_date=None)`
Creates or updates a worker's wage rate entry in the database.
```python
wage_rate = ensure_worker_wage_rate('EMP001', 'general labor', 'Stride Staffing')
```

#### `populate_missing_wage_rates(timesheet_df=None)`
Finds and populates missing wage rates for all workers based on timesheet data.
```python
summary = populate_missing_wage_rates()
# Returns: {"workers_processed": 45, "wage_rates_created": 12, "wage_rates_updated": 3}
```

#### `add_new_worker_with_wage_rate(worker_id, position, agency_name, name=None, effective_date=None)`
Convenience function to add a new worker with automatic wage rate assignment.
```python
result = add_new_worker_with_wage_rate('EMP002', 'forklift driver', 'JJ Staffing', 'John Doe')
```

## Usage Examples

### 1. Adding a New Worker Programmatically
```python
from app.utils import add_new_worker_with_wage_rate

# Add a new forklift driver from JJ Staffing
result = add_new_worker_with_wage_rate(
    worker_id='FLT001',
    position='forklift driver',
    agency_name='JJ Staffing',
    name='John Smith'
)

print(result['message'])  # "Worker FLT001 created with wage rate $22.50/hr"
```

### 2. Updating Existing Worker Wage Rates
```python
from app.utils import ensure_worker_wage_rate

# Update a worker's position and recalculate wage rate
wage_rate = ensure_worker_wage_rate(
    worker_id='EMP001',
    position='forklift driver',  # Promoted from general labor
    agency_name='JJ Staffing',
    effective_date=date.today()
)
```

### 3. Bulk Population of Missing Wage Rates
```python
from app.utils import populate_missing_wage_rates

# Process all workers and fill in missing wage rates
summary = populate_missing_wage_rates()

print(f"Processed {summary['workers_processed']} workers")
print(f"Created {summary['wage_rates_created']} new wage rates")
print(f"Updated {summary['wage_rates_updated']} existing wage rates")
```

## Scripts Provided

### 1. `populate_wage_rates.py`
Standalone script to populate missing wage rates in the database.

**Usage:**
```bash
# Preview changes without applying them
python populate_wage_rates.py --dry-run

# Apply changes to the database
python populate_wage_rates.py
```

**Features:**
- Analyzes current database state
- Shows summary of workers with/without wage rates
- Processes all workers from timesheet data
- Supports dry-run mode for safe preview

### 2. `example_wage_rate_usage.py`
Demonstration script showing how to use all the new functions.

**Usage:**
```bash
python example_wage_rate_usage.py
```

## Integration with Existing System

### 1. CSV Upload Process
The existing CSV upload in `app/routes/dashboard.py` has been enhanced to:
- Automatically create wage rates for new workers
- Use database-driven markup lookup instead of hardcoded values
- Handle errors gracefully with informative messages

### 2. Database Schema
Works with existing tables:
- `Worker`: Stores basic worker information
- `WageRate`: Stores calculated wage rates with effective dates
- `Agency`: Stores agency information
- `AgencyMarkup`: Stores markup rates with effective dates

### 3. Backward Compatibility
- Existing wage rate records are preserved
- Old hardcoded markup functions still available for legacy code
- No changes required to existing timesheet processing

## Configuration

### Base Rates
Defined in `app/validation.py`:
```python
def get_base_rate_for_position(position):
    if normalized_position == 'general labor':
        return 16.0
    elif normalized_position == 'forklift driver':
        return 18.0
```

### Agency Markups
Stored in database via `AgencyMarkup` table:
- Supports multiple markup rates per agency with effective dates
- Most recent rate for a given date is automatically selected
- Managed through the existing agency management interface

## Error Handling

The system includes comprehensive error handling:
- Invalid positions are rejected with clear error messages
- Missing agencies log warnings and default to 0% markup
- Database errors are caught and logged appropriately
- Dry-run mode available for safe testing

## Best Practices

### 1. When Adding New Workers
- Always specify both position and agency
- Use the `add_new_worker_with_wage_rate()` function for consistency
- Provide effective dates for historical accuracy

### 2. When Updating Wage Rates
- Use `ensure_worker_wage_rate()` to maintain data integrity
- Consider effective dates for historical tracking
- Test changes with dry-run mode first

### 3. For Bulk Operations
- Use `populate_missing_wage_rates()` for comprehensive updates
- Monitor the summary output for errors
- Run during low-activity periods to avoid conflicts

## Troubleshooting

### Common Issues

1. **"Agency not found in database"**
   - Ensure the agency exists in the `Agency` table
   - Check for exact name matching (case-sensitive)
   - Add missing agencies through the management interface

2. **"No markup found for agency"**
   - Add markup records in the `AgencyMarkup` table
   - Ensure effective dates are set correctly
   - Check that the effective date is not in the future

3. **"Unknown position"**
   - Use only 'general labor' or 'forklift driver'
   - Position names are case-insensitive but must match exactly
   - Check `VALID_POSITIONS` in `app/validation.py`

### Debug Mode
Enable detailed logging by setting the Flask app to debug mode:
```python
app.config['DEBUG'] = True
```

This will show detailed information about wage rate calculations and database operations in the logs.