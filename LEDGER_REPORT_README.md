# Ledger Report Functionality

This document describes the ledger report functionality that has been implemented in the ERP Billing Engine.

## Overview

The ledger report provides a proper double-entry bookkeeping ledger format showing all transactions for a specific account with running balances, date filtering, and print capabilities.

## Features

### 1. Proper Ledger Format
- Shows opening balance at the start of the period
- Displays all transactions chronologically
- Calculates running balance after each transaction
- Shows closing balance at the end of the period
- Follows standard accounting principles for debit/credit impacts

### 2. Date Filtering
- Default date range: Current fiscal year start to today
- Custom date range selection with date pickers
- Opening balance automatically calculated based on selected start date

### 3. Print Functionality
- Print-optimized layout with proper formatting
- Company header information
- Summary information included
- Clean table formatting for printing

### 4. Account Balance Logic
- **Assets & Expenses**: Debits increase balance, Credits decrease balance
- **Liabilities, Equity & Revenue**: Credits increase balance, Debits decrease balance
- Opening balances are considered from fiscal year settings

## URL Structure

```
/bookkeeping/ledger-report/<account_id>/
```

## Usage

### Accessing Ledger Reports

1. Navigate to the Ledger Accounts list at `/bookkeeping/ledger_accounts/`
2. Click the "Ledger Report" button for any account
3. The report will show transactions for the current fiscal year by default

### Filtering by Date

1. Use the date filter form at the top of the report
2. Select start and end dates
3. Click "Apply Filter" to update the report

### Printing

1. Click the "Print Report" button
2. The browser's print dialog will open
3. The report will be formatted for printing with:
   - Company header
   - Account information
   - Transaction table
   - Summary information

## Technical Implementation

### View: `LedgerReportView`
- Handles date filtering and validation
- Calculates opening balances
- Processes transactions and running balances
- Renders the report template

### Template: `ledger_report.html`
- Responsive design for mobile and desktop
- Print-optimized CSS
- Date filtering form
- Summary cards showing key metrics
- Detailed transaction table

### Key Methods

#### `get_opening_balance(account, start_date)`
- Retrieves opening balance from `LedgerOpeningBalance` model
- Calculates accumulated balance from fiscal year start to report start date
- Returns balance amount and type (DEBIT/CREDIT)

#### `get_transactions(account, start_date, end_date)`
- Retrieves all journal entry lines for the account within date range
- Orders transactions chronologically
- Returns formatted transaction data

## Database Models Used

- `LedgerAccount`: Account information
- `JournalEntry`: Transaction headers
- `JournalEntryLine`: Individual transaction lines
- `LedgerOpeningBalance`: Opening balances per fiscal year
- `FiscalYear`: Fiscal year settings

## Example Usage

```python
# Access the ledger report
GET /bookkeeping/ledger-report/123e4567-e89b-12d3-a456-426614174000/

# Filter by date range
GET /bookkeeping/ledger-report/123e4567-e89b-12d3-a456-426614174000/?start_date=2024-01-01&end_date=2024-12-31

# Print view
GET /bookkeeping/ledger-report/123e4567-e89b-12d3-a456-426614174000/?print=true
```

## Benefits

1. **Accurate Financial Reporting**: Proper double-entry bookkeeping principles
2. **User-Friendly Interface**: Easy date filtering and navigation
3. **Print-Ready**: Professional formatting for printed reports
4. **Responsive Design**: Works on mobile and desktop devices
5. **Performance Optimized**: Efficient queries with proper indexing

## Security

- User authentication required (`AuthMixin`)
- Company-specific data isolation
- Permission-based access control
- Account access restricted to user's company

## Future Enhancements

1. Export to PDF functionality
2. Export to Excel/CSV
3. Multiple account comparison
4. Trial balance integration
5. Chart of accounts navigation
6. Account hierarchy display
