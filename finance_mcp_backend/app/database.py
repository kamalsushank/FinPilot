"""SQLite persistence layer for the Finance MCP project.

All SQL is parameterized. The database is stored at the project root as finance.db.
"""
import json
import sqlite3
import calendar
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "finance.db"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    return connection


def _iso_date(value: str, field_name: str = "date") -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format") from exc


def initialize_database() -> None:
    """Create tables and safely migrate older databases."""
    with get_connection() as connection:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            amount REAL NOT NULL CHECK(amount > 0),
            category TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            transaction_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            due_date TEXT NOT NULL,
            is_recurring INTEGER NOT NULL DEFAULT 0 CHECK(is_recurring IN (0, 1)),
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'paid'))
        );

        CREATE TABLE IF NOT EXISTS recurring_bill_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            day_of_month INTEGER NOT NULL CHECK(day_of_month BETWEEN 1 AND 31),
            start_date TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'sent', 'cancelled')),
            bill_id INTEGER,
            FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_name TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            quantity REAL NOT NULL CHECK(quantity > 0),
            purchase_price REAL NOT NULL CHECK(purchase_price > 0),
            purchase_date TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            frequency TEXT NOT NULL DEFAULT 'one-time',
            start_date TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','closed')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_user_investments_user ON user_investments(user_id, status);

        CREATE TABLE IF NOT EXISTS investment_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            risk_level TEXT NOT NULL DEFAULT 'varies',
            liquidity TEXT NOT NULL DEFAULT 'varies',
            eligibility TEXT NOT NULL DEFAULT 'Check official provider rules',
            summary TEXT NOT NULL DEFAULT '',
            official_url TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, category)
        );

        CREATE TABLE IF NOT EXISTS user_financial_profiles (
            user_id TEXT PRIMARY KEY,
            monthly_income REAL,
            monthly_expenses REAL,
            monthly_savings REAL,
            emergency_fund REAL,
            outstanding_debt REAL,
            goal TEXT NOT NULL DEFAULT '',
            time_horizon TEXT NOT NULL DEFAULT '',
            risk_tolerance TEXT NOT NULL DEFAULT '',
            eligibility_notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Migration for an older bills table.
        bill_columns = {row["name"] for row in connection.execute("PRAGMA table_info(bills)")}
        if "recurring_template_id" not in bill_columns:
            connection.execute("""
                ALTER TABLE bills ADD COLUMN recurring_template_id INTEGER
                REFERENCES recurring_bill_templates(id)
            """)
        connection.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_recurring_bill_date
            ON bills(recurring_template_id, due_date)
        """)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_bills_status_due ON bills(status, due_date)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date)")

        # Starter catalogue entries are broad categories, not personalized recommendations.
        starter_products = [
            ("Public Provident Fund (PPF)", "Government small-savings scheme", "low market risk",
             "long lock-in; withdrawals restricted", "Eligibility and contribution rules must be checked",
             "Long-term government-backed savings product; rates and rules can change.",
             "https://www.nsiindia.gov.in/"),
            ("National Savings Certificate (NSC)", "Government small-savings scheme", "low market risk",
             "fixed tenure", "Check current post-office rules and eligibility",
             "Fixed-tenure small-savings product; verify current rate and tax treatment.",
             "https://www.indiapost.gov.in/"),
            ("Sukanya Samriddhi Account", "Government small-savings scheme", "low market risk",
             "restricted until specified conditions", "For eligible girl child accounts; age and guardian rules apply",
             "Purpose-specific small-savings account; strict eligibility and withdrawal rules apply.",
             "https://www.indiapost.gov.in/"),
            ("Post Office Monthly Income Scheme", "Government small-savings scheme", "low market risk",
             "fixed tenure and premature-closure rules", "Check current post-office rules",
             "Designed to provide periodic interest income; confirm current terms.",
             "https://www.indiapost.gov.in/"),
            ("Bank Fixed Deposit", "Bank deposit", "low market risk; bank-specific risks apply",
             "depends on deposit and premature-withdrawal rules", "Depends on bank and product",
             "A fixed-term bank deposit. Compare rates, penalties and deposit-insurance limits.",
             "https://www.rbi.org.in/"),
            ("Mutual Funds", "Market-linked investment", "varies by fund",
             "usually redeemable subject to fund rules; some have exit loads/lock-ins",
             "KYC and scheme eligibility apply",
             "Returns are market-linked. Review the scheme information document, costs and riskometer.",
             "https://www.amfiindia.com/"),
            ("Direct Equity / Shares", "Market-linked investment", "high; market prices fluctuate",
             "market liquidity varies", "Demat/trading account and market rules apply",
             "Direct stock investing can lose capital; requires research and risk management.",
             "https://www.sebi.gov.in/"),
            ("LIC / Life Insurance Products", "Insurance", "product-specific",
             "product-specific; surrender terms may apply", "Depends on policy terms",
             "Insurance and investment features vary by policy. Compare protection, costs, guarantees and surrender terms.",
             "https://licindia.in/"),
            ("National Pension System (NPS)", "Retirement investment", "market-linked; depends on allocation",
             "retirement-oriented withdrawal restrictions", "Check current PFRDA eligibility and rules",
             "Retirement-focused account with allocation and withdrawal rules; confirm current rules.",
             "https://www.pfrda.org.in/"),
            ("Sovereign Gold Bonds / Gold options", "Gold exposure", "gold-price and product-specific risks",
             "depends on instrument; SGB issuance/redemption rules change",
             "Availability and eligibility depend on the instrument",
             "Gold exposure is not guaranteed to appreciate; verify current issuance and liquidity.",
             "https://www.rbi.org.in/"),
        ]
        connection.executemany("""
            INSERT OR IGNORE INTO investment_products
            (name, category, risk_level, liquidity, eligibility, summary, official_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, starter_products)


def add_transaction(transaction_type: str, amount: float, category: str,
                    description: str = "", transaction_date: str | None = None) -> dict:
    if transaction_type not in ("income", "expense"):
        raise ValueError("Type must be income or expense")
    if amount <= 0:
        raise ValueError("Amount must be positive")
    category = category.strip()
    if not category:
        raise ValueError("Category cannot be empty")
    tx_date = _iso_date(transaction_date or date.today().isoformat(), "transaction_date")
    with get_connection() as connection:
        cursor = connection.execute("""
            INSERT INTO transactions(type, amount, category, description, transaction_date)
            VALUES (?, ?, ?, ?, ?)
        """, (transaction_type, float(amount), category, (description or "").strip(), tx_date))
        return {"id": cursor.lastrowid, "type": transaction_type, "amount": float(amount),
                "category": category, "description": (description or "").strip(),
                "transaction_date": tx_date}


def list_transactions(limit: int = 50) -> list[dict]:
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT * FROM transactions ORDER BY transaction_date DESC, id DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(row) for row in rows]


def get_financial_summary(month: str | None = None) -> dict:
    """Return income, expenses and balance. Optional month format: YYYY-MM."""
    parameters: tuple[Any, ...] = ()
    where = ""
    if month:
        try:
            datetime.strptime(month, "%Y-%m")
        except ValueError as exc:
            raise ValueError("month must use YYYY-MM format") from exc
        where = "WHERE substr(transaction_date, 1, 7) = ?"
        parameters = (month,)
    with get_connection() as connection:
        row = connection.execute(f"""
            SELECT
                COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS expenses
            FROM transactions {where}
        """, parameters).fetchone()
    income, expenses = round(row["income"], 2), round(row["expenses"], 2)
    return {"month": month or "all_time", "income": income, "expenses": expenses,
            "balance": round(income - expenses, 2)}


def add_bill(name: str, amount: float, due_date: str, is_recurring: bool = False) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("Bill name cannot be empty")
    if amount <= 0:
        raise ValueError("Bill amount must be positive")
    due = _iso_date(due_date, "due_date")
    with get_connection() as connection:
        cursor = connection.execute("""
            INSERT INTO bills(name, amount, due_date, is_recurring, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (name, float(amount), due, int(bool(is_recurring))))
        return {"id": cursor.lastrowid, "name": name, "amount": float(amount),
                "due_date": due, "is_recurring": bool(is_recurring), "status": "pending"}


def list_bills(status: str = "all") -> list[dict]:
    if status not in ("all", "pending", "paid"):
        raise ValueError("Status must be all, pending, or paid")
    with get_connection() as connection:
        if status == "all":
            rows = connection.execute("SELECT * FROM bills ORDER BY due_date, id").fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM bills WHERE status=? ORDER BY due_date, id", (status,)
            ).fetchall()
        return [dict(row) for row in rows]


def mark_bill_paid(bill_id: int) -> dict:
    with get_connection() as connection:
        cursor = connection.execute("UPDATE bills SET status='paid' WHERE id=?", (bill_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Bill with ID {bill_id} was not found")
        return {"id": bill_id, "status": "paid"}


def add_recurring_bill_template(name: str, amount: float, day_of_month: int,
                                start_date: str | None = None) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("Recurring bill name cannot be empty")
    if amount <= 0:
        raise ValueError("Amount must be positive")
    if not isinstance(day_of_month, int) or not 1 <= day_of_month <= 31:
        raise ValueError("day_of_month must be an integer between 1 and 31")
    start = _iso_date(start_date or date.today().isoformat(), "start_date")
    with get_connection() as connection:
        cursor = connection.execute("""
            INSERT INTO recurring_bill_templates(name, amount, day_of_month, start_date, active)
            VALUES (?, ?, ?, ?, 1)
        """, (name, float(amount), day_of_month, start))
        template_id = cursor.lastrowid
    # Generate the initial rolling window immediately.
    generate_recurring_bills(months_ahead=2, today=date.today())
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM recurring_bill_templates WHERE id=?", (template_id,)
        ).fetchone()
    return dict(row)


def list_recurring_bill_templates(active_only: bool = False) -> list[dict]:
    with get_connection() as connection:
        if active_only:
            rows = connection.execute(
                "SELECT * FROM recurring_bill_templates WHERE active=1 ORDER BY id"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM recurring_bill_templates ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]


def set_recurring_bill_template_active(template_id: int, active: bool) -> dict:
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE recurring_bill_templates SET active=? WHERE id=?",
            (int(active), template_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Recurring bill template {template_id} was not found")
        row = connection.execute(
            "SELECT * FROM recurring_bill_templates WHERE id=?", (template_id,)
        ).fetchone()
        return dict(row)


def _due_date_for_month(year: int, month: int, requested_day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(requested_day, last_day))


def generate_recurring_bills(months_ahead: int = 2, today: date | None = None) -> dict:
    """Idempotently create recurring occurrences from each start month through N months ahead."""
    if not 0 <= months_ahead <= 24:
        raise ValueError("months_ahead must be between 0 and 24")
    today = today or date.today()
    target_index = today.year * 12 + today.month - 1 + months_ahead
    target_year, target_month0 = divmod(target_index, 12)
    target_month = target_month0 + 1
    created = 0
    with get_connection() as connection:
        templates = connection.execute(
            "SELECT * FROM recurring_bill_templates WHERE active=1"
        ).fetchall()
        for template in templates:
            start = date.fromisoformat(template["start_date"])
            start_index = start.year * 12 + start.month - 1
            end_index = target_year * 12 + target_month - 1
            for month_index in range(start_index, end_index + 1):
                year, month0 = divmod(month_index, 12)
                month = month0 + 1
                due = _due_date_for_month(year, month, template["day_of_month"])
                # Do not create a due date earlier than the template's explicit start date.
                if due < start:
                    continue
                cursor = connection.execute("""
                    INSERT OR IGNORE INTO bills
                    (name, amount, due_date, is_recurring, status, recurring_template_id)
                    VALUES (?, ?, ?, 1, 'pending', ?)
                """, (template["name"], template["amount"], due.isoformat(), template["id"]))
                created += cursor.rowcount
    return {"created": created, "months_ahead": months_ahead}


def get_upcoming_bills(limit: int = 2) -> list[dict]:
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT id, name, amount, due_date, status, is_recurring, recurring_template_id
            FROM bills
            WHERE status='pending'
            ORDER BY due_date ASC, id ASC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(row) for row in rows]


def add_reminder(message: str, scheduled_at: str, bill_id: int | None = None) -> dict:
    message = message.strip()
    if not message:
        raise ValueError("Reminder message cannot be empty")
    try:
        scheduled = datetime.fromisoformat(scheduled_at).isoformat(timespec="seconds")
    except (TypeError, ValueError) as exc:
        raise ValueError("scheduled_at must use ISO format, e.g. 2026-10-30T09:00:00") from exc
    with get_connection() as connection:
        if bill_id is not None and connection.execute(
            "SELECT id FROM bills WHERE id=?", (bill_id,)
        ).fetchone() is None:
            raise ValueError(f"Bill with ID {bill_id} was not found")
        cursor = connection.execute("""
            INSERT INTO reminders(message, scheduled_at, status, bill_id)
            VALUES (?, ?, 'pending', ?)
        """, (message, scheduled, bill_id))
        return {"id": cursor.lastrowid, "message": message, "scheduled_at": scheduled,
                "status": "pending", "bill_id": bill_id}


def list_reminders(status: str = "all") -> list[dict]:
    if status not in ("all", "pending", "sent", "cancelled"):
        raise ValueError("Status must be all, pending, sent, or cancelled")
    with get_connection() as connection:
        if status == "all":
            rows = connection.execute("SELECT * FROM reminders ORDER BY scheduled_at, id").fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM reminders WHERE status=? ORDER BY scheduled_at, id", (status,)
            ).fetchall()
        return [dict(row) for row in rows]


def cancel_reminder(reminder_id: int) -> dict:
    with get_connection() as connection:
        cursor = connection.execute("""
            UPDATE reminders SET status='cancelled'
            WHERE id=? AND status='pending'
        """, (reminder_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Pending reminder with ID {reminder_id} was not found")
        return {"id": reminder_id, "status": "cancelled"}


def upsert_financial_profile(user_id: str, data: dict) -> dict:
    user_id = (user_id or "default").strip()
    allowed = {"monthly_income", "monthly_expenses", "monthly_savings", "emergency_fund",
               "outstanding_debt", "goal", "time_horizon", "risk_tolerance", "eligibility_notes"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Unknown profile fields: {', '.join(sorted(unknown))}")
    for key in ("monthly_income", "monthly_expenses", "monthly_savings", "emergency_fund", "outstanding_debt"):
        value = data.get(key)
        if value is not None and value < 0:
            raise ValueError(f"{key} cannot be negative")
    existing = get_financial_profile(user_id) or {}
    merged = {key: data.get(key, existing.get(key)) for key in allowed}
    with get_connection() as connection:
        connection.execute("""
            INSERT INTO user_financial_profiles
            (user_id, monthly_income, monthly_expenses, monthly_savings, emergency_fund,
             outstanding_debt, goal, time_horizon, risk_tolerance, eligibility_notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
             monthly_income=excluded.monthly_income, monthly_expenses=excluded.monthly_expenses,
             monthly_savings=excluded.monthly_savings, emergency_fund=excluded.emergency_fund,
             outstanding_debt=excluded.outstanding_debt, goal=excluded.goal,
             time_horizon=excluded.time_horizon, risk_tolerance=excluded.risk_tolerance,
             eligibility_notes=excluded.eligibility_notes, updated_at=CURRENT_TIMESTAMP
        """, (user_id, merged["monthly_income"], merged["monthly_expenses"],
              merged["monthly_savings"], merged["emergency_fund"], merged["outstanding_debt"],
              merged["goal"] or "", merged["time_horizon"] or "", merged["risk_tolerance"] or "",
              merged["eligibility_notes"] or ""))
    return get_financial_profile(user_id) or {"user_id": user_id}


def get_financial_profile(user_id: str = "default") -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM user_financial_profiles WHERE user_id=?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def list_investment_products(category: str | None = None) -> list[dict]:
    with get_connection() as connection:
        if category:
            rows = connection.execute("""
                SELECT * FROM investment_products
                WHERE category LIKE ? OR name LIKE ?
                ORDER BY category, name
            """, (f"%{category}%", f"%{category}%")).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM investment_products ORDER BY category, name"
            ).fetchall()
        return [dict(row) for row in rows]


def add_investment_product(name: str, category: str, risk_level: str = "varies",
                           liquidity: str = "varies", eligibility: str = "",
                           summary: str = "", official_url: str = "") -> dict:
    if not name.strip() or not category.strip():
        raise ValueError("Product name and category are required")
    with get_connection() as connection:
        connection.execute("""
            INSERT INTO investment_products(name, category, risk_level, liquidity,
                eligibility, summary, official_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name, category) DO UPDATE SET
                risk_level=excluded.risk_level, liquidity=excluded.liquidity,
                eligibility=excluded.eligibility, summary=excluded.summary,
                official_url=excluded.official_url, updated_at=CURRENT_TIMESTAMP
        """, (name.strip(), category.strip(), risk_level.strip(), liquidity.strip(),
              eligibility.strip(), summary.strip(), official_url.strip()))
        row = connection.execute(
            "SELECT * FROM investment_products WHERE name=? AND category=?",
            (name.strip(), category.strip())
        ).fetchone()
        return dict(row)


def get_spending_by_category(category: str, user_id: str | None = None) -> dict:
    """Calculate expenses matching a category from persisted transaction rows."""
    category = (category or "").strip()
    if not category:
        raise ValueError("Please specify an expense category, such as food or travel.")
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT id, amount, category, description, transaction_date
            FROM transactions WHERE type='expense'
              AND (lower(category) LIKE ? OR lower(description) LIKE ?)
            ORDER BY transaction_date DESC, id DESC
        """, (f"%{category.lower()}%", f"%{category.lower()}%") ).fetchall()
    items = [dict(row) for row in rows]
    return {"category": category, "total": round(sum(float(x["amount"]) for x in items), 2),
            "count": len(items), "transactions": items}


def add_user_investment(user_id: str, product_name: str, asset_type: str, amount: float,
                        frequency: str = "one-time", start_date: str | None = None,
                        notes: str = "", source_url: str = "") -> dict:
    if not product_name.strip() or not asset_type.strip() or float(amount) <= 0:
        raise ValueError("A product name, investment type, and positive amount are required.")
    start = _iso_date(start_date or date.today().isoformat(), "start_date")
    with get_connection() as connection:
        cur = connection.execute("""INSERT INTO user_investments
            (user_id, product_name, asset_type, amount, frequency, start_date, notes, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, product_name.strip(), asset_type.strip(), float(amount), frequency.strip(), start, notes.strip(), source_url.strip()))
        row = connection.execute("SELECT * FROM user_investments WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)


def list_user_investments(user_id: str = "default") -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM user_investments WHERE user_id=? AND status='active' ORDER BY start_date DESC, id DESC", (user_id,)).fetchall()
        return [dict(row) for row in rows]


def close_user_investment(investment_id: int, user_id: str = "default") -> bool:
    with get_connection() as connection:
        cur = connection.execute("UPDATE user_investments SET status='closed' WHERE id=? AND user_id=?", (investment_id, user_id))
        return cur.rowcount > 0
