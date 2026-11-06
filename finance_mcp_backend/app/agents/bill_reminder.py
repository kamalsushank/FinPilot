"""Bill & Reminder sub-agent. It stores reminders but does not send notifications."""
from app.database import (
    add_bill, list_bills, mark_bill_paid, get_upcoming_bills,
    add_recurring_bill_template, list_recurring_bill_templates,
    set_recurring_bill_template_active, generate_recurring_bills,
    add_reminder, list_reminders, cancel_reminder,
)


def upcoming_bills(limit: int = 2) -> list[dict]:
    generate_recurring_bills(months_ahead=2)
    return get_upcoming_bills(limit)


def pending_bills() -> list[dict]:
    generate_recurring_bills(months_ahead=2)
    return list_bills("pending")


def create_bill(name: str, amount: float, due_date: str) -> dict:
    return add_bill(name, amount, due_date, False)


def create_recurring_bill(name: str, amount: float, day_of_month: int,
                          start_date: str | None = None) -> dict:
    return add_recurring_bill_template(name, amount, day_of_month, start_date)


def pay_bill(bill_id: int) -> dict:
    return mark_bill_paid(bill_id)


def templates(active_only: bool = False) -> list[dict]:
    return list_recurring_bill_templates(active_only)


def set_template_active(template_id: int, active: bool) -> dict:
    return set_recurring_bill_template_active(template_id, active)


def generate(months_ahead: int = 2) -> dict:
    return generate_recurring_bills(months_ahead)


def create_reminder(message: str, scheduled_at: str, bill_id: int | None = None) -> dict:
    return add_reminder(message, scheduled_at, bill_id)


def reminders(status: str = "all") -> list[dict]:
    return list_reminders(status)


def cancel(reminder_id: int) -> dict:
    return cancel_reminder(reminder_id)
