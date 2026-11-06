"""MCP tools wrapping the same business logic used by FastAPI."""
from datetime import date

from mcp.server import MCPServer

from app.database import (
    initialize_database,
    add_transaction as save_transaction,
    get_financial_summary as read_summary,
    add_bill as save_bill,
    list_bills as read_bills,
    mark_bill_paid as update_bill_paid,
    get_upcoming_bills as read_upcoming_bills,
    add_recurring_bill_template as save_recurring_template,
    list_recurring_bill_templates as read_recurring_templates,
    set_recurring_bill_template_active as set_template_active,
    generate_recurring_bills as generate_bills,
    add_reminder as save_reminder,
    list_reminders as read_reminders,
    cancel_reminder as update_reminder_cancelled,
    list_investment_products as read_investment_products,
    upsert_financial_profile,
)
from app.agents.investment import recommend_investments
from app.agents.manager import chat as manager_chat

server = MCPServer("Financial Management MCP Server")


@server.tool()
def add_transaction(transaction_type: str, amount: float, category: str,
                    description: str = "", transaction_date: str = "") -> dict:
    """Record income or an expense. Date uses YYYY-MM-DD; omitted date means today."""
    if transaction_type not in ("income", "expense"):
        raise ValueError("Type must be income or expense")
    if amount <= 0:
        raise ValueError("Amount must be positive")
    parsed_date = date.fromisoformat(transaction_date).isoformat() if transaction_date else date.today().isoformat()
    return save_transaction(transaction_type, amount, category, description, parsed_date)


@server.tool()
def get_financial_summary(month: str = "") -> dict:
    """Return income, expenses and cash-flow balance; optionally filter by YYYY-MM."""
    return read_summary(month or None)


@server.tool()
def add_bill(name: str, amount: float, due_date: str, is_recurring: bool = False) -> dict:
    """Add a one-off bill. For repeating monthly bills, use add_recurring_bill_template."""
    return save_bill(name, amount, due_date, is_recurring)


@server.tool()
def list_bills(status: str = "all") -> list[dict]:
    """List bills. status can be all, pending, or paid."""
    return read_bills(status)


@server.tool()
def mark_bill_paid(bill_id: int) -> dict:
    """Mark a bill paid by its database ID."""
    return update_bill_paid(bill_id)


@server.tool()
def get_upcoming_bills(limit: int = 2) -> list[dict]:
    """Generate missing recurring bill occurrences, then return nearest unpaid bills."""
    generate_bills(months_ahead=2)
    return read_upcoming_bills(limit)


@server.tool()
def add_recurring_bill_template(name: str, amount: float, day_of_month: int,
                                start_date: str = "") -> dict:
    """Create a monthly recurring bill rule. Day 29-31 clamps to the month's last day when needed."""
    start = date.fromisoformat(start_date).isoformat() if start_date else date.today().isoformat()
    return save_recurring_template(name, amount, day_of_month, start)


@server.tool()
def list_recurring_bill_templates(active_only: bool = False) -> list[dict]:
    """List monthly recurring bill rules."""
    return read_recurring_templates(active_only)


@server.tool()
def set_recurring_bill_active(template_id: int, active: bool) -> dict:
    """Activate or deactivate future bill generation for a recurring template."""
    return set_template_active(template_id, active)


@server.tool()
def generate_recurring_bills(months_ahead: int = 2) -> dict:
    """Create any missing monthly bill occurrences through the requested future window."""
    return generate_bills(months_ahead)


@server.tool()
def add_reminder(message: str, scheduled_at: str, bill_id: int | None = None) -> dict:
    """Store a reminder record; this does not send push notifications."""
    return save_reminder(message, scheduled_at, bill_id)


@server.tool()
def list_reminders(status: str = "all") -> list[dict]:
    """List stored reminders by status."""
    return read_reminders(status)


@server.tool()
def cancel_reminder(reminder_id: int) -> dict:
    """Cancel a pending reminder."""
    return update_reminder_cancelled(reminder_id)


@server.tool()
def list_investment_products(category: str = "") -> list[dict]:
    """List the saved investment catalogue, optionally filtered by category."""
    return read_investment_products(category or None)


@server.tool()
def save_investment_profile(user_id: str, profile_json: str) -> dict:
    """Save user financial suitability details. profile_json must be a JSON object string."""
    import json
    data = json.loads(profile_json)
    if not isinstance(data, dict):
        raise ValueError("profile_json must encode a JSON object")
    return upsert_financial_profile(user_id, data)


@server.tool()
def research_investments(user_id: str, request: str) -> dict:
    """Research relevant India-focused investment options using Gemini Search grounding when configured."""
    return recommend_investments(user_id, request)


@server.tool()
def ask_finance_manager(message: str, user_id: str = "default") -> dict:
    """Route a natural-language finance question to the manager/investment agent."""
    return manager_chat(message, user_id)


if __name__ == "__main__":
    initialize_database()
    generate_bills(months_ahead=2)
    server.run()
