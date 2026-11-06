"""Natural-language manager for the personal finance assistant."""
import json
import re
from datetime import date

from app.agents.model_client import generate_text, gemini_enabled
from app.agents.investment import recommend_investments
from app.database import list_investment_products, get_spending_by_category
from app.agents.money_tracker import record_transaction, summary as money_summary
from app.agents.bill_reminder import (
    upcoming_bills, pending_bills, create_bill, create_recurring_bill, pay_bill,
)

ALLOWED_ACTIONS = {
    "summary", "category_spending", "list_bills", "upcoming_bills", "list_investments",
    "investment_recommendation", "add_transaction", "add_bill",
    "add_recurring_bill", "mark_bill_paid", "help", "multiple_transactions"
}


def _fallback_transactions(message: str) -> list[dict]:
    """Extract explicit amount clauses; conjunctions may omit a repeated verb."""
    text = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", message.lower())
    amount_pattern = re.compile(r"(?:₹|rs\.?\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:rupees?)?", re.I)
    verb_pattern = re.compile(r"\b(earned|received|got|made|spent|paid|bought|purchased)\b", re.I)
    amounts = list(amount_pattern.finditer(text))
    found = []
    current_type = None
    for i, match in enumerate(amounts):
        prefix = text[:match.start()]
        verbs = list(verb_pattern.finditer(prefix))
        if verbs:
            verb = verbs[-1].group(1).lower()
            current_type = "income" if verb in ("earned", "received", "got", "made") else "expense"
        if current_type is None:
            continue
        next_start = amounts[i + 1].start() if i + 1 < len(amounts) else len(text)
        desc = text[match.end():next_start].strip(" ,.;:-")
        desc = re.sub(r"^(?:on|for|from|towards|as)\s+", "", desc)
        desc = re.sub(r"\s+and\s*$", "", desc).strip()
        # A description can end in a conjunction only when the next amount follows.
        desc = re.sub(r"\b(?:then|and)$", "", desc).strip(" ,.;:-")
        desc = desc or ("income" if current_type == "income" else "general expense")
        found.append({"transaction_type": current_type, "amount": float(match.group(1)),
                      "category": desc[:100], "description": desc[:100],
                      "transaction_date": date.today().isoformat()})
    return found


def _deterministic_route(message: str) -> dict:
    text = message.lower()
    transactions = _fallback_transactions(message)
    if len(transactions) > 1:
        return {"action": "multiple_transactions", "arguments": {"transactions": transactions}}
    if len(transactions) == 1:
        return {"action": "add_transaction", "arguments": transactions[0]}
    if any(word in text for word in ("catalogue", "catalog", "investment options", "list investment")):
        return {"action": "list_investments", "arguments": {}}
    if any(word in text for word in ("invest", "mutual fund", "lic", "scheme", "ppf", "nps", "stocks", "insurance")):
        return {"action": "investment_recommendation", "arguments": {}}
    if "bill" in text and any(word in text for word in ("upcoming", "due", "next", "show", "list")):
        return {"action": "upcoming_bills", "arguments": {}}
    # Specific category questions must query matching expense rows, not the overall summary.
    match = re.search(r"(?:spent|spend|expenses? on|amount on)\s+(?:on\s+)?([a-z][a-z &-]{1,35}?)(?:[?.!,]|$)", text)
    if match and any(w in text for w in ("how much", "total", "spent", "spend", "expense")):
        category = match.group(1).strip()
        category = re.sub(r"\b(food|foods|groceries|grocery)\b", "food", category)
        return {"action": "category_spending", "arguments": {"category": category}}
    if any(word in text for word in ("summary", "balance", "income", "expense", "expenses")):
        return {"action": "summary", "arguments": {}}
    if "bill" in text:
        return {"action": "list_bills", "arguments": {}}
    return {"action": "help", "arguments": {}}


def _model_route(message: str) -> dict:
    prompt = f"""
You are the intent and transaction extraction component of an India-focused personal finance app.
Return ONLY valid JSON with keys: action, arguments, clarification.
Allowed actions: summary, category_spending, list_bills, upcoming_bills, list_investments, investment_recommendation,
add_transaction, multiple_transactions, add_bill, add_recurring_bill, mark_bill_paid, help.
For one or more explicit income/expense entries in a single message, use multiple_transactions with
arguments.transactions as an array. Each item must contain transaction_type (income or expense),
amount (number in INR), category, description, transaction_date (YYYY-MM-DD).
Examples:
- "I earned ₹5000 from a project, spent ₹100 on food and ₹200 on clothes" -> multiple_transactions with 3 entries.
- "I spent 250 on groceries today" -> add_transaction with one expense entry.
- "I earned 5000 from freelancing" -> add_transaction with one income entry.
- "Add Wi-Fi bill 799 due on 2026-11-28 every month" -> add_recurring_bill with name, amount, day_of_month, start_date.
- "I want to invest ₹500 monthly for 10 years; compare mutual funds, government schemes and life insurance" -> investment_recommendation.
- "What bills are due next?" -> upcoming_bills.
Allowed arguments for add_bill: name, amount, due_date (YYYY-MM-DD).
Allowed arguments for add_recurring_bill: name, amount, day_of_month (1-31), start_date (YYYY-MM-DD).
Allowed arguments for mark_bill_paid: bill_id (integer).
If a required detail is missing or uncertain, do not invent it; use help and provide one concise clarification question.
Investment requests must never write transactions or bills. Do not claim a transaction was saved; this is only extraction.
Today's date is {date.today().isoformat()}.
User message: {message}
"""
    try:
        raw, _ = generate_text(prompt)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return _deterministic_route(message)
        payload = json.loads(match.group())
        action = payload.get("action")
        args = payload.get("arguments") or {}
        if action not in ALLOWED_ACTIONS or not isinstance(args, dict):
            return _deterministic_route(message)
        return {"action": action, "arguments": args, "clarification": payload.get("clarification")}
    except Exception:
        return _deterministic_route(message)


def _money(value: float) -> str:
    return f"₹{value:,.2f}".removesuffix(".00")


def _save_transaction(args: dict) -> dict:
    required = ("transaction_type", "amount", "category", "transaction_date")
    if any(args.get(key) in (None, "") for key in required):
        raise ValueError("I need the amount, whether it was income or an expense, and the date to save this entry.")
    amount = float(args["amount"])
    if amount <= 0:
        raise ValueError("The transaction amount must be greater than zero.")
    tx_type = str(args["transaction_type"]).lower()
    if tx_type not in ("income", "expense"):
        raise ValueError("I couldn't tell whether that entry was income or an expense. Please clarify.")
    return record_transaction(tx_type, amount, str(args["category"]), str(args.get("description", "")), str(args["transaction_date"]))


def chat(message: str, user_id: str = "default") -> dict:
    message = (message or "").strip()
    if not message:
        raise ValueError("Please enter a message.")
    if len(message) > 5000:
        raise ValueError("Your message is too long (maximum 5000 characters).")

    routed = _model_route(message) if gemini_enabled() else _deterministic_route(message)
    action = routed["action"]
    args = routed.get("arguments") or {}
    clarification = routed.get("clarification")
    if clarification:
        return {"response": str(clarification), "action": "clarification_needed", "sources": []}

    if action == "multiple_transactions":
        entries = args.get("transactions")
        if not isinstance(entries, list) or not entries:
            return {"response": "I couldn't confidently identify the transactions. Try writing each one with an amount, such as ‘I earned ₹5,000 from a project and spent ₹100 on food.’", "action": "clarification_needed", "sources": []}
        try:
            for item in entries:
                if not isinstance(item, dict):
                    raise ValueError("one of the entries was not understood")
                if any(item.get(key) in (None, "") for key in ("transaction_type", "amount", "category", "transaction_date")):
                    raise ValueError("one entry is missing its type, amount, category, or date")
                if str(item["transaction_type"]).lower() not in ("income", "expense") or float(item["amount"]) <= 0:
                    raise ValueError("one entry has an invalid type or amount")
        except (ValueError, TypeError, KeyError) as error:
            return {"response": f"I haven't saved any of these entries because one detail is unclear: {error}. Please clarify the message and try again.", "action": "clarification_needed", "sources": []}
        saved = []
        for item in entries:
            saved.append(_save_transaction(item))
        lines = []
        for item in entries:
            label = item.get("description") or item.get("category") or "transaction"
            verb = "Income" if item.get("transaction_type") == "income" else "Expense"
            lines.append(f"• {verb}: {_money(float(item['amount']))} — {label}")
        return {"response": f"I've recorded {len(saved)} transactions in your finance database:\n" + "\n".join(lines) + "\n\nYour dashboard has been refreshed.", "action": action, "sources": []}

    if action == "add_transaction":
        try:
            saved = _save_transaction(args)
        except (ValueError, TypeError, KeyError) as error:
            return {"response": f"I couldn't save that transaction yet. {error}", "action": "clarification_needed", "sources": []}
        kind = "income" if args["transaction_type"] == "income" else "expense"
        label = args.get("description") or args.get("category") or "transaction"
        return {"response": f"I've recorded {_money(float(args['amount']))} as {kind} for {label}. Your finance dashboard has been refreshed.", "action": action, "sources": []}

    if action == "category_spending":
        category = str(args.get("category", "")).strip()
        if not category:
            return {"response": "Which category should I check, for example food, travel or clothes?", "action": "clarification_needed", "sources": []}
        result = get_spending_by_category(category)
        if not result["count"]:
            return {"response": f"I couldn't find any recorded expenses matching '{category}'. This only checks transactions saved in your finance database; it doesn't assume unrecorded spending.", "action": action, "data": result, "sources": []}
        return {"response": f"You've spent {_money(result['total'])} on {category} across {result['count']} recorded transaction(s).\n\n" + "\n".join(f"• {_money(x['amount'])} — {x.get('description') or x.get('category')} ({x['transaction_date']})" for x in result['transactions']), "action": action, "data": result, "sources": []}

    if action == "summary":
        result = money_summary()
        if isinstance(result, dict):
            income = result.get("total_income", result.get("income", 0))
            expenses = result.get("total_expenses", result.get("expenses", 0))
            balance = result.get("balance", result.get("net_balance", float(income or 0) - float(expenses or 0)))
            return {"response": f"Here's your financial summary: total income is {_money(float(income or 0))}, total expenses are {_money(float(expenses or 0))}, and your net balance is {_money(float(balance or 0))}.", "action": action, "data": result, "sources": []}
        return {"response": f"Here's your financial summary: {result}", "action": action, "data": result, "sources": []}

    if action in ("list_bills", "upcoming_bills"):
        rows = pending_bills() if action == "list_bills" else upcoming_bills(2)
        if not rows:
            return {"response": "You don't have any unpaid bills recorded right now.", "action": action, "data": rows, "sources": []}
        lines = []
        for bill in rows:
            name = bill.get("name", "Bill")
            amount = bill.get("amount", 0)
            due = bill.get("due_date", "a date not recorded")
            lines.append(f"• {name}: {_money(float(amount or 0))}, due {due}")
        return {"response": "Here are your unpaid bills:\n" + "\n".join(lines), "action": action, "data": rows, "sources": []}

    if action == "list_investments":
        rows = list_investment_products()
        if not rows:
            return {"response": "There are no investment options in the local catalogue yet. Ask me to research a goal, time horizon and monthly budget for current options.", "action": action, "data": rows, "sources": []}
        lines = [f"• {row.get('name', 'Option')} ({row.get('category', 'investment')}) — {row.get('summary', 'Details need verification.') }" for row in rows[:12]]
        return {"response": "The local catalogue currently includes:\n" + "\n".join(lines) + "\n\nThe catalogue may not reflect current rates or availability; ask for research if you need up-to-date information.", "action": action, "data": rows, "sources": []}

    if action == "investment_recommendation":
        result = recommend_investments(user_id, message)
        answer = result.get("answer") or result.get("message")
        if not answer:
            # Fallback catalogue output is still expressed as readable prose, not a Python object.
            products = result.get("catalogue", [])
            names = ", ".join(p.get("name", "an option") for p in products[:8]) or "government schemes, deposits, mutual funds, insurance and retirement options"
            answer = (f"I haven't performed live investment research because the AI search service isn't configured. "
                      f"I can show the local catalogue ({names}), but it may be out of date. Set GEMINI_API_KEY to enable current source-backed research.")
        return {"response": answer, "action": action, "sources": result.get("sources", []),
                "recommendations": result.get("recommendations", []),
                "financial_context": result.get("financial_context", {}), "mode": result.get("mode")}

    if action == "add_bill":
        if any(args.get(k) in (None, "") for k in ("name", "amount", "due_date")):
            return {"response": "Please tell me the bill name, amount, and due date. For example: ‘My electricity bill is ₹900 due on 5 November.’", "action": "clarification_needed", "sources": []}
        result = create_bill(str(args["name"]), float(args["amount"]), str(args["due_date"]))
        return {"response": f"I've added the {args['name']} bill for {_money(float(args['amount']))}, due on {args['due_date']}.", "action": action, "data": result, "sources": []}

    if action == "add_recurring_bill":
        if any(args.get(k) in (None, "") for k in ("name", "amount", "day_of_month")):
            return {"response": "Please provide the bill name, amount, and day of the month it is due. For example: ‘Wi-Fi costs ₹799 every month, due on the 28th.’", "action": "clarification_needed", "sources": []}
        result = create_recurring_bill(str(args["name"]), float(args["amount"]), int(args["day_of_month"]), str(args.get("start_date") or date.today().isoformat()))
        return {"response": f"I've saved {args['name']} as a recurring bill for {_money(float(args['amount']))}, due on day {int(args['day_of_month'])} each month. Upcoming occurrences will be generated without duplicates.", "action": action, "data": result, "sources": []}

    if action == "mark_bill_paid":
        if not args.get("bill_id"):
            return {"response": "Which bill should I mark as paid? You can mention its bill ID or name.", "action": "clarification_needed", "sources": []}
        result = pay_bill(int(args["bill_id"]))
        return {"response": f"I've updated bill #{args['bill_id']} as paid.", "action": action, "data": result, "sources": []}

    return {"response": "You can tell me about income or expenses in plain English, ask about your balance or upcoming bills, add a bill, mark a bill paid, or ask for investment research. For example: ‘I earned ₹5,000 from a project, spent ₹100 on food and ₹200 on clothes.’", "action": "help", "sources": []}
