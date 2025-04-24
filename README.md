# Warehouse Tracker

A Flask web application for tracking and managing warehouse worker timesheets. This application helps warehouse managers monitor work hours, prevent overtime, and generate agency summaries.

## Features

- **CSV Upload/Export**: Upload timesheet CSV files and export processed data
- **Dashboard**: Weekly summary of worker hours with overtime alerts
- **Detailed Entries**: View and edit individual timesheet entries
- **Agency Summary**: Track total regular and overtime hours by agency

## Installation

1. Clone the repository:
   ```
   git clone [repository-url]
   cd warehouse_tracker
   ```

2. Create a virtual environment and activate it:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

1. Start the application:
   ```
   python run.py
   ```

2. Open your web browser and navigate to:
   ```
   http://127.0.0.1:5000/
   ```

3. Upload a CSV file with the following columns:
   - `worker_id`: Unique identifier for the worker
   - `date`: Work date (YYYY-MM-DD)
   - `time_in`: Clock-in time (HH:MM)
   - `time_out`: Clock-out time (HH:MM)
   - `lunch_minutes`: Lunch break duration in minutes (optional, defaults to 30)
   - `Agency`: Agency name (required for agency summary)

## CSV Format Example

```
worker_id,date,time_in,time_out,lunch_minutes,Agency
W001,2023-06-01,08:00,16:30,30,AgencyA
W002,2023-06-01,09:00,17:30,45,AgencyB
```

## Development

- The application uses Flask as the web framework
- Pandas is used for data processing and analysis
- Bootstrap is used for the frontend UI

## License

This project is licensed under the MIT License - see the LICENSE file for details.
