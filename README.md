# Warehouse Tracker

A Flask web application for tracking and managing warehouse worker timesheets and cargo volume. This application helps warehouse managers monitor work hours, prevent overtime, analyze cargo handling efficiency, and generate agency summaries.

## Features

- **CSV Upload/Export**: Upload timesheet and cargo volume CSV files directly from the dashboard. Export processed data.
- **Dashboard**: Weekly summary of worker hours with overtime alerts.
- **Cargo/Worker Relationship Analysis**: Visualize the relationship between cargo volume (by MAWB or carton count) and worker hours/labors, with interactive time span controls (day, month, year).
- **Detailed Entries**: View and edit individual timesheet entries.
- **Agency Summary**: Track total regular and overtime hours by agency.

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

4. Initialize the database (for cargo volume data):
   ```
   python
   >>> from run import init_db
   >>> init_db()
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

3. **Upload Data from the Dashboard:**
   - **Timesheet CSV**: Columns required:
     - `worker_id`: Unique identifier for the worker
     - `date`: Work date (YYYY-MM-DD or M/D/YY)
     - `time_in`: Clock-in time (HH:MM)
     - `time_out`: Clock-out time (HH:MM)
     - `lunch_minutes`: Lunch break duration in minutes (optional, defaults to 30)
     - `Agency`: Agency name (required for agency summary)
   - **Cargo Volume CSV**: Columns required:
     - `Date`: Cargo date (MM/DD/YYYY or M/D/YY)
     - `MAWB`: Unique order identifier (if repeated, only the first date is counted)
     - `Carton Number`: Total carton number for that MAWB

4. **Analyze Data:**
   - Use the "Cargo Relationship" page to visualize the relationship between cargo volume and worker hours/labors, with options to aggregate by day, month, or year.

## CSV Format Example

**Timesheet:**
```
worker_id,date,time_in,time_out,lunch_minutes,Agency
W001,2023-06-01,08:00,16:30,30,AgencyA
W002,2023-06-01,09:00,17:30,45,AgencyB
```

**Cargo Volume:**
```
Date,MAWB,Carton Number
6/1/2023,1234567890,50
6/1/2023,1234567891,30
6/2/2023,1234567890,20  # Only the first date for each MAWB is counted
```

## Development

- The application uses Flask as the web framework
- Pandas is used for data processing and analysis
- SQLAlchemy is used for cargo volume database storage
- Bootstrap is used for the frontend UI

## License

This project is licensed under the MIT License - see the LICENSE file for details.
