# Agency Summary Tests

This directory contains tests for the Agency Summary feature, focusing on validating the accuracy of labor hours calculations.

## What's Being Tested

These tests verify that the Agency Summary functions correctly calculate:

1. **Regular Hours**: Should be capped at 40 hours per worker per week
2. **Overtime Hours**: Any hours above 40 per worker per week
3. **Total Hours**: The sum of regular and overtime hours
4. **Agency and Month Grouping**: Correctly aggregates by agency and month

## Test Cases

- `test_calculate_daily_hours`: Ensures daily hours are calculated correctly (time_out - time_in - lunch)
- `test_regular_vs_overtime_calculation`: Tests overtime threshold (>40 hours/week)
- `test_multi_agency_breakdown`: Tests that hours are attributed to the correct agencies
- `test_month_grouping`: Tests monthly aggregation of hours
- `test_zero_hours_edge_case`: Tests handling of empty data
- `test_integration_agency_summary_route_mock`: Basic route testing

## Running the Tests

To run all the non-database tests:
```
python -m pytest tests/test_agency_summary.py::test_calculate_daily_hours tests/test_agency_summary.py::test_regular_vs_overtime_calculation tests/test_agency_summary.py::test_multi_agency_breakdown tests/test_agency_summary.py::test_month_grouping tests/test_agency_summary.py::test_zero_hours_edge_case -v
```

The integration test requires a working database and may fail in some environments:
```
python -m pytest tests/test_agency_summary.py::test_integration_agency_summary_route_mock -v
```

## Adding New Tests

When adding new tests:

1. **Test Data**: Create test data fixtures in the test file (like `simple_timesheet_data`) 
2. **Avoid Database Dependency**: Where possible, make tests work without requiring database access
3. **Use Verification Pattern**: Test calculations by verifying properties that must be true, rather than exact numbers

## Test Design Notes

- The tests use controlled, artificial data to ensure predictable results
- Fixtures provide data for different testing scenarios
- Each test checks a specific aspect of the calculation logic
- We validate using precise assertions (equal) or mathematical properties (sum of X equals Y) 