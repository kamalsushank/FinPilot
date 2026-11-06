"""Grounded investment research and user holdings helpers."""
import json, re
from app.database import (get_financial_profile, list_investment_products, upsert_financial_profile,
    get_financial_summary, get_spending_by_category)
from app.agents.model_client import generate_text, gemini_enabled

def update_profile(user_id: str, profile: dict) -> dict:
    return upsert_financial_profile(user_id, profile)

def catalogue() -> list[dict]:
    return list_investment_products()

def recommend_investments(user_id: str, request: str) -> dict:
    profile = get_financial_profile(user_id) or {}
    products = list_investment_products()
    summary = get_financial_summary()
    available_balance = float(summary.get("balance", 0) or 0)
    catalogue_text = "\n".join(f"- {p['name']} | {p['category']} | {p['risk_level']} | {p['liquidity']} | {p['eligibility']} | {p['summary']} | {p['official_url']}" for p in products)
    if not gemini_enabled():
        return {"mode":"unavailable", "answer":"Live investment research is unavailable because GEMINI_API_KEY is not configured. I have not invented or guessed any current schemes, rates, funds, or share recommendations. Configure the key and try again.", "recommendations":[], "sources":[], "financial_context":{"recorded_net_balance":available_balance}}
    prompt = f"""You are an India-focused investment research assistant. Use Google Search grounding.
User request: {request}
Recorded finances from SQLite: all-time net balance ₹{available_balance:,.2f}; recorded income ₹{summary.get('income',0):,.2f}; recorded expenses ₹{summary.get('expenses',0):,.2f}. This balance is not automatically investable cash; explain that upcoming bills, emergency savings, debt and monthly cash flow must be considered.
Known profile: {json.dumps(profile, ensure_ascii=False)}
Local catalogue (discovery hints only, not proof of current availability):
{catalogue_text}
Research relevant current individual options, not just generic categories. Consider mutual funds (specific schemes and direct/regular + growth/IDCW distinctions when relevant), government small-savings schemes, bank deposits, LIC/life insurance only when protection need is stated, listed shares only if user explicitly seeks equities, and other suitable regulated options. Use official sources first: AMFI, SEBI, RBI, India Post/NSI, PFRDA, LIC and issuer scheme documents. Verify product existence, current availability, risk, lock-in, minimum investment, fees and dates. Never fabricate returns/rates or guarantee performance. Do not recommend buying insurance as an investment substitute; distinguish term protection from savings policies. Never infer risk tolerance if not given.
Return ONLY JSON: {{"answer":"Readable Markdown explaining suitability, affordability caveats and comparison","recommendations":[{{"name":"exact product/scheme/fund/share name","type":"Mutual fund / Government scheme / Insurance / Equity / Deposit / Other","risk":"...","minimum_investment":"...","time_horizon":"...","why_it_may_fit":"...","key_risks":"...","liquidity_or_lock_in":"...","current_status":"verified status or not confirmed","source_url":"official URL"}}]}}. Include only individually researched options with evidence. If exact option details cannot be verified, say so. Aim for a useful shortlist, not an exhaustive dump.
"""
    try:
        raw, sources = generate_text(prompt, use_google_search=True)
        match = re.search(r"\{.*\}", raw, re.S)
        payload = json.loads(match.group()) if match else {"answer":raw,"recommendations":[]}
        answer = payload.get("answer") or raw
        recs = payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []
        clean=[]
        for r in recs:
            if isinstance(r,dict) and r.get("name"):
                clean.append({k:str(r.get(k,"Not verified")) for k in ("name","type","risk","minimum_investment","time_horizon","why_it_may_fit","key_risks","liquidity_or_lock_in","current_status","source_url")})
        return {"mode":"live_research","answer":answer,"recommendations":clean,"sources":sources,"financial_context":{"recorded_net_balance":available_balance}}
    except Exception as exc:
        return {"mode":"research_error","answer":f"I couldn't complete live investment research because the search/model service returned an error. No investment was added and no recommendation has been fabricated. Please check the backend's Gemini configuration and logs, then retry. Technical detail: {type(exc).__name__}.","recommendations":[],"sources":[],"financial_context":{"recorded_net_balance":available_balance}}
