"""Money Tracker sub-agent: deterministic operations on income and expenses."""
from app.database import add_transaction, get_financial_summary, list_transactions


def record_transaction(transaction_type: str, amount: float, category: str,
                       description: str = "", transaction_date: str | None = None) -> dict:
    return add_transaction(transaction_type, amount, category, description, transaction_date)


def summary(month: str | None = None) -> dict:
    return get_financial_summary(month)


def recent_transactions(limit: int = 50) -> list[dict]:
    return list_transactions(limit)
