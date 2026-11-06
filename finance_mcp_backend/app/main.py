"""FastAPI HTTP API used by the web frontend."""
from contextlib import asynccontextmanager
from datetime import date
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict

from app.database import (
    initialize_database, add_transaction, list_transactions, get_financial_summary,
    add_bill, list_bills, mark_bill_paid, get_upcoming_bills,
    add_recurring_bill_template, list_recurring_bill_templates,
    set_recurring_bill_template_active, generate_recurring_bills,
    add_reminder, list_reminders, cancel_reminder,
    get_financial_profile, upsert_financial_profile,
    list_investment_products, add_investment_product,
    add_user_investment, list_user_investments, close_user_investment,
)
from app.agents.manager import chat as manager_chat
from app.agents.investment import recommend_investments

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    # Keep a small rolling window of bill occurrences ready on startup.
    generate_recurring_bills(months_ahead=2)
    yield


app = FastAPI(
    title="Multi-Agent Financial Management System",
    version="1.0.0",
    description=(
        "Finance API with SQLite, recurring bills, MCP tools, Gemini-powered routing, "
        "and grounded investment research."
    ),
    lifespan=lifespan,
)

allowed_origins = [
    item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000").split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TransactionRequest(BaseModel):
    type: str = Field(pattern="^(income|expense)$")
    amount: float = Field(gt=0)
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    transaction_date: date = Field(default_factory=date.today)


class BillRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    amount: float = Field(gt=0)
    due_date: date
    is_recurring: bool = False


class RecurringBillRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    amount: float = Field(gt=0)
    day_of_month: int = Field(ge=1, le=31)
    start_date: date = Field(default_factory=date.today)


class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    monthly_income: float | None = Field(default=None, ge=0)
    monthly_expenses: float | None = Field(default=None, ge=0)
    monthly_savings: float | None = Field(default=None, ge=0)
    emergency_fund: float | None = Field(default=None, ge=0)
    outstanding_debt: float | None = Field(default=None, ge=0)
    goal: str | None = Field(default=None, max_length=500)
    time_horizon: str | None = Field(default=None, max_length=100)
    risk_tolerance: str | None = Field(default=None, max_length=100)
    eligibility_notes: str | None = Field(default=None, max_length=1000)


class ReminderRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    scheduled_at: str
    bill_id: int | None = Field(default=None, gt=0)


class InvestmentProductRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=120)
    risk_level: str = "varies"
    liquidity: str = "varies"
    eligibility: str = ""
    summary: str = ""
    official_url: str = ""


class UserInvestmentRequest(BaseModel):
    user_id: str = Field(default="demo", min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=200)
    asset_type: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0)
    frequency: str = Field(default="one-time", max_length=50)
    start_date: date = Field(default_factory=date.today)
    notes: str = Field(default="", max_length=1000)
    source_url: str = Field(default="", max_length=1000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    user_id: str = Field(default="default", min_length=1, max_length=100)


def _run(callable_, *args, **kwargs):
    try:
        return callable_(*args, **kwargs)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/health")
def health():
    from app.agents.model_client import gemini_enabled, get_model_name
    return {
        "status": "ok",
        "database": "sqlite",
        "gemini_configured": gemini_enabled(),
        "gemini_model": get_model_name() if gemini_enabled() else None,
    }


@app.post("/transactions")
def create_transaction(request: TransactionRequest):
    return _run(
        add_transaction, request.type, request.amount, request.category,
        request.description, request.transaction_date.isoformat()
    )


@app.get("/transactions")
def transactions(limit: int = Query(default=50, ge=1, le=500)):
    return _run(list_transactions, limit)


@app.get("/summary")
def financial_summary(month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$")):
    return _run(get_financial_summary, month)


@app.post("/bills")
def create_bill(request: BillRequest):
    return _run(add_bill, request.name, request.amount, request.due_date.isoformat(), request.is_recurring)


@app.get("/bills")
def bills(status: str = Query(default="all", pattern="^(all|pending|paid)$")):
    return _run(list_bills, status)


@app.post("/bills/{bill_id}/pay")
def pay_bill(bill_id: int):
    return _run(mark_bill_paid, bill_id)


@app.get("/bills/upcoming")
def upcoming_bills(limit: int = Query(default=2, ge=1, le=10)):
    # Generate before listing, so opening dashboard keeps the rolling window current.
    _run(generate_recurring_bills, 2)
    return _run(get_upcoming_bills, limit)


@app.post("/bills/recurring")
def create_recurring_bill(request: RecurringBillRequest):
    return _run(
        add_recurring_bill_template,
        request.name, request.amount, request.day_of_month, request.start_date.isoformat()
    )


@app.get("/bills/recurring")
def recurring_templates(active_only: bool = False):
    return list_recurring_bill_templates(active_only)


@app.patch("/bills/recurring/{template_id}")
def update_recurring_template(template_id: int, active: bool = Query(...)):
    return _run(set_recurring_bill_template_active, template_id, active)


@app.post("/bills/recurring/generate")
def generate_bills(months_ahead: int = Query(default=2, ge=0, le=24)):
    return _run(generate_recurring_bills, months_ahead)


@app.post("/reminders")
def create_reminder(request: ReminderRequest):
    return _run(add_reminder, request.message, request.scheduled_at, request.bill_id)


@app.get("/reminders")
def reminders(status: str = Query(default="all", pattern="^(all|pending|sent|cancelled)$")):
    return _run(list_reminders, status)


@app.post("/reminders/{reminder_id}/cancel")
def cancel_existing_reminder(reminder_id: int):
    return _run(cancel_reminder, reminder_id)


@app.get("/investments/catalogue")
def investment_catalogue(category: str | None = None):
    return list_investment_products(category)


@app.post("/investments/catalogue")
def save_investment_product(request: InvestmentProductRequest):
    return _run(add_investment_product, **request.model_dump())


@app.get("/investments/profile/{user_id}")
def read_investment_profile(user_id: str):
    return get_financial_profile(user_id) or {"user_id": user_id, "profile_exists": False}


@app.put("/investments/profile/{user_id}")
def save_investment_profile(user_id: str, request: ProfileRequest):
    data = {key: value for key, value in request.model_dump().items() if value is not None}
    return _run(upsert_financial_profile, user_id, data)


@app.post("/investments/recommend")
def investment_recommendation(request: ChatRequest):
    return _run(recommend_investments, request.user_id, request.message)


@app.get("/investments/holdings/{user_id}")
def investment_holdings(user_id: str):
    return list_user_investments(user_id)


@app.post("/investments/holdings")
def create_investment_holding(request: UserInvestmentRequest):
    data = request.model_dump()
    data["start_date"] = request.start_date.isoformat()
    return _run(add_user_investment, **data)


@app.delete("/investments/holdings/{investment_id}")
def close_investment_holding(investment_id: int, user_id: str = Query(default="demo")):
    if not close_user_investment(investment_id, user_id):
        raise HTTPException(status_code=404, detail="Investment holding not found")
    return {"success": True, "message": "Investment marked as closed."}


@app.post("/chat")
def chat(request: ChatRequest):
    return _run(manager_chat, request.message, request.user_id)
