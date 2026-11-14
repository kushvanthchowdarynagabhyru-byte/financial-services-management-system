# Financial Services Management System

Simple command-line base project (Python 3 + SQLite, no extra installs).

## Run
    python financial_services.py

The database file `financial_services.db` is created automatically on first run.

## Features
- Customers: add, list, search
- Accounts: open savings/current, view balance
- Transactions: deposit, withdraw, transfer, statement
- Loans: apply (EMI calculated), pay EMI, view loans

## Configuration (top of financial_services.py)
- MIN_BALANCE: minimum balance per account type
- LOAN_RATES: annual interest rate per loan type
