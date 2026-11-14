"""
Financial Services Management System
------------------------------------
A simple command-line base project using Python + SQLite.

Modules:
  1. Customer management  (add, list, search)
  2. Account management   (open savings/current account, view balance)
  3. Transactions         (deposit, withdraw, transfer, statement)
  4. Loans                (apply with EMI calculation, repay, list)

Run:  python financial_services.py
"""

import os
import sqlite3
from datetime import datetime

DB_FILE = os.environ.get("FSMS_DB", "financial_services.db")
MIN_BALANCE = {"savings": 500.0, "current": 0.0}
LOAN_RATES = {"personal": 12.0, "home": 8.5, "vehicle": 9.5}  # annual %


# ----------------------------------------------------------------- database
def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                name     TEXT NOT NULL,
                phone    TEXT NOT NULL UNIQUE,
                email    TEXT,
                address  TEXT,
                created  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS accounts (
                acc_no      INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                acc_type    TEXT NOT NULL CHECK (acc_type IN ('savings','current')),
                balance     REAL NOT NULL DEFAULT 0,
                opened      TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                acc_no    INTEGER NOT NULL REFERENCES accounts(acc_no),
                tx_type   TEXT NOT NULL,
                amount    REAL NOT NULL,
                balance   REAL NOT NULL,
                note      TEXT,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS loans (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                loan_type   TEXT NOT NULL,
                principal   REAL NOT NULL,
                rate        REAL NOT NULL,
                months      INTEGER NOT NULL,
                emi         REAL NOT NULL,
                outstanding REAL NOT NULL,
                status      TEXT NOT NULL DEFAULT 'active',
                created     TEXT NOT NULL
            );
            """
        )


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- customers
def add_customer(name, phone, email="", address=""):
    if not name.strip() or not phone.strip():
        raise ValueError("Name and phone are required.")
    try:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO customers (name, phone, email, address, created) "
                "VALUES (?,?,?,?,?)",
                (name.strip(), phone.strip(), email.strip(), address.strip(), now()),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("A customer with this phone number already exists.")


def list_customers(keyword=""):
    with get_conn() as conn:
        like = f"%{keyword}%"
        return conn.execute(
            "SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY id",
            (like, like),
        ).fetchall()


def get_customer(cid):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
    if not row:
        raise ValueError("Customer not found.")
    return row


# ----------------------------------------------------------------- accounts
def open_account(customer_id, acc_type, initial_deposit=0.0):
    acc_type = acc_type.lower()
    if acc_type not in MIN_BALANCE:
        raise ValueError("Account type must be 'savings' or 'current'.")
    get_customer(customer_id)
    if initial_deposit < MIN_BALANCE[acc_type]:
        raise ValueError(
            f"Minimum opening balance for {acc_type} is {MIN_BALANCE[acc_type]:.2f}."
        )
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO accounts (customer_id, acc_type, balance, opened) "
            "VALUES (?,?,?,?)",
            (customer_id, acc_type, initial_deposit, now()),
        )
        acc_no = cur.lastrowid
        if initial_deposit > 0:
            conn.execute(
                "INSERT INTO transactions (acc_no, tx_type, amount, balance, note, timestamp) "
                "VALUES (?,?,?,?,?,?)",
                (acc_no, "DEPOSIT", initial_deposit, initial_deposit, "Opening deposit", now()),
            )
    return acc_no


def get_account(acc_no, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        row = conn.execute("SELECT * FROM accounts WHERE acc_no=?", (acc_no,)).fetchone()
    finally:
        if own:
            conn.close()
    if not row:
        raise ValueError(f"Account {acc_no} not found.")
    return row


def customer_accounts(customer_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM accounts WHERE customer_id=?", (customer_id,)
        ).fetchall()


# ------------------------------------------------------------- transactions
def _record(conn, acc_no, tx_type, amount, new_balance, note=""):
    conn.execute("UPDATE accounts SET balance=? WHERE acc_no=?", (new_balance, acc_no))
    conn.execute(
        "INSERT INTO transactions (acc_no, tx_type, amount, balance, note, timestamp) "
        "VALUES (?,?,?,?,?,?)",
        (acc_no, tx_type, amount, new_balance, note, now()),
    )


def _check_amount(amount):
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")


def deposit(acc_no, amount, note="Cash deposit"):
    _check_amount(amount)
    with get_conn() as conn:
        acc = get_account(acc_no, conn)
        new_bal = acc["balance"] + amount
        _record(conn, acc_no, "DEPOSIT", amount, new_bal, note)
    return new_bal


def withdraw(acc_no, amount, note="Cash withdrawal"):
    _check_amount(amount)
    with get_conn() as conn:
        acc = get_account(acc_no, conn)
        new_bal = acc["balance"] - amount
        if new_bal < MIN_BALANCE[acc["acc_type"]]:
            raise ValueError(
                f"Insufficient funds. Minimum balance for {acc['acc_type']} "
                f"account is {MIN_BALANCE[acc['acc_type']]:.2f}."
            )
        _record(conn, acc_no, "WITHDRAW", amount, new_bal, note)
    return new_bal


def transfer(from_acc, to_acc, amount):
    _check_amount(amount)
    if from_acc == to_acc:
        raise ValueError("Cannot transfer to the same account.")
    with get_conn() as conn:  # single transaction: both legs or neither
        src = get_account(from_acc, conn)
        dst = get_account(to_acc, conn)
        src_bal = src["balance"] - amount
        if src_bal < MIN_BALANCE[src["acc_type"]]:
            raise ValueError("Insufficient funds for transfer.")
        _record(conn, from_acc, "TRANSFER_OUT", amount, src_bal, f"To A/C {to_acc}")
        _record(conn, to_acc, "TRANSFER_IN", amount, dst["balance"] + amount,
                f"From A/C {from_acc}")
    return src_bal


def statement(acc_no, limit=20):
    with get_conn() as conn:
        get_account(acc_no, conn)
        return conn.execute(
            "SELECT * FROM transactions WHERE acc_no=? ORDER BY id DESC LIMIT ?",
            (acc_no, limit),
        ).fetchall()


# -------------------------------------------------------------------- loans
def calc_emi(principal, annual_rate, months):
    r = annual_rate / 12 / 100
    if r == 0:
        return principal / months
    f = (1 + r) ** months
    return principal * r * f / (f - 1)


def apply_loan(customer_id, loan_type, principal, months):
    loan_type = loan_type.lower()
    if loan_type not in LOAN_RATES:
        raise ValueError(f"Loan type must be one of: {', '.join(LOAN_RATES)}.")
    _check_amount(principal)
    if months < 1:
        raise ValueError("Tenure must be at least 1 month.")
    get_customer(customer_id)
    rate = LOAN_RATES[loan_type]
    emi = calc_emi(principal, rate, months)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO loans (customer_id, loan_type, principal, rate, months, emi, "
            "outstanding, created) VALUES (?,?,?,?,?,?,?,?)",
            (customer_id, loan_type, principal, rate, months, emi, emi * months, now()),
        )
        return cur.lastrowid, rate, emi


def repay_loan(loan_id, acc_no):
    """Pay one EMI from the given account."""
    with get_conn() as conn:
        loan = conn.execute("SELECT * FROM loans WHERE id=?", (loan_id,)).fetchone()
        if not loan:
            raise ValueError("Loan not found.")
        if loan["status"] != "active":
            raise ValueError("Loan is already closed.")
        acc = get_account(acc_no, conn)
        if acc["customer_id"] != loan["customer_id"]:
            raise ValueError("Account does not belong to the loan holder.")
        pay = min(loan["emi"], loan["outstanding"])
        new_bal = acc["balance"] - pay
        if new_bal < MIN_BALANCE[acc["acc_type"]]:
            raise ValueError("Insufficient funds to pay EMI.")
        _record(conn, acc_no, "LOAN_EMI", pay, new_bal, f"EMI for loan #{loan_id}")
        outstanding = round(loan["outstanding"] - pay, 2)
        status = "closed" if outstanding <= 0.01 else "active"
        conn.execute(
            "UPDATE loans SET outstanding=?, status=? WHERE id=?",
            (max(outstanding, 0), status, loan_id),
        )
    return pay, max(outstanding, 0), status


def list_loans(customer_id=None):
    with get_conn() as conn:
        if customer_id:
            return conn.execute(
                "SELECT * FROM loans WHERE customer_id=?", (customer_id,)
            ).fetchall()
        return conn.execute("SELECT * FROM loans").fetchall()


# ---------------------------------------------------------------------- CLI
def ask_int(prompt):
    while True:
        try:
            return int(input(prompt).strip())
        except ValueError:
            print("  Please enter a whole number.")


def ask_float(prompt):
    while True:
        try:
            return float(input(prompt).strip())
        except ValueError:
            print("  Please enter a valid number.")


def menu_customers():
    print("\n1. Add customer\n2. List / search customers\n3. Back")
    ch = input("Choice: ").strip()
    if ch == "1":
        cid = add_customer(
            input("Name: "), input("Phone: "), input("Email: "), input("Address: ")
        )
        print(f"  Customer created. ID = {cid}")
    elif ch == "2":
        rows = list_customers(input("Search (blank = all): ").strip())
        print(f"\n{'ID':<5}{'Name':<22}{'Phone':<15}{'Email'}")
        for r in rows:
            print(f"{r['id']:<5}{r['name']:<22}{r['phone']:<15}{r['email']}")
        if not rows:
            print("  No customers found.")


def menu_accounts():
    print("\n1. Open account\n2. View customer accounts\n3. Check balance\n4. Back")
    ch = input("Choice: ").strip()
    if ch == "1":
        cid = ask_int("Customer ID: ")
        t = input("Type (savings/current): ")
        amt = ask_float("Opening deposit: ")
        print(f"  Account opened. A/C No = {open_account(cid, t, amt)}")
    elif ch == "2":
        cid = ask_int("Customer ID: ")
        print(f"  Customer: {get_customer(cid)['name']}")
        for a in customer_accounts(cid):
            print(f"  A/C {a['acc_no']}  {a['acc_type']:<8} Balance: {a['balance']:.2f}")
    elif ch == "3":
        a = get_account(ask_int("Account No: "))
        print(f"  Balance: {a['balance']:.2f}")


def menu_transactions():
    print("\n1. Deposit\n2. Withdraw\n3. Transfer\n4. Statement\n5. Back")
    ch = input("Choice: ").strip()
    if ch == "1":
        bal = deposit(ask_int("Account No: "), ask_float("Amount: "))
        print(f"  Deposited. New balance: {bal:.2f}")
    elif ch == "2":
        bal = withdraw(ask_int("Account No: "), ask_float("Amount: "))
        print(f"  Withdrawn. New balance: {bal:.2f}")
    elif ch == "3":
        bal = transfer(ask_int("From A/C: "), ask_int("To A/C: "), ask_float("Amount: "))
        print(f"  Transferred. Your new balance: {bal:.2f}")
    elif ch == "4":
        rows = statement(ask_int("Account No: "))
        print(f"\n{'Date':<21}{'Type':<14}{'Amount':>10}{'Balance':>12}  Note")
        for r in rows:
            print(f"{r['timestamp']:<21}{r['tx_type']:<14}{r['amount']:>10.2f}"
                  f"{r['balance']:>12.2f}  {r['note']}")
        if not rows:
            print("  No transactions.")


def menu_loans():
    print("\n1. Apply for loan\n2. Pay EMI\n3. View loans\n4. Back")
    ch = input("Choice: ").strip()
    if ch == "1":
        print(f"  Rates: {', '.join(f'{k} {v}%' for k, v in LOAN_RATES.items())}")
        lid, rate, emi = apply_loan(
            ask_int("Customer ID: "), input("Loan type: "),
            ask_float("Principal: "), ask_int("Tenure (months): "),
        )
        print(f"  Loan #{lid} approved at {rate}% p.a. Monthly EMI: {emi:.2f}")
    elif ch == "2":
        pay, out, status = repay_loan(ask_int("Loan ID: "), ask_int("Pay from A/C: "))
        print(f"  Paid {pay:.2f}. Outstanding: {out:.2f} ({status})")
    elif ch == "3":
        raw = input("Customer ID (blank = all): ").strip()
        loans = list_loans(int(raw) if raw else None)
        print(f"\n{'ID':<5}{'Cust':<6}{'Type':<10}{'Principal':>12}{'EMI':>10}"
              f"{'Outstanding':>13}  Status")
        for l in loans:
            print(f"{l['id']:<5}{l['customer_id']:<6}{l['loan_type']:<10}"
                  f"{l['principal']:>12.2f}{l['emi']:>10.2f}{l['outstanding']:>13.2f}"
                  f"  {l['status']}")
        if not loans:
            print("  No loans found.")


def main():
    init_db()
    actions = {
        "1": menu_customers,
        "2": menu_accounts,
        "3": menu_transactions,
        "4": menu_loans,
    }
    while True:
        print("\n===== FINANCIAL SERVICES MANAGEMENT SYSTEM =====")
        print("1. Customers\n2. Accounts\n3. Transactions\n4. Loans\n5. Exit")
        ch = input("Choice: ").strip()
        if ch == "5":
            print("Goodbye!")
            break
        action = actions.get(ch)
        if not action:
            print("  Invalid choice.")
            continue
        try:
            action()
        except ValueError as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    main()
