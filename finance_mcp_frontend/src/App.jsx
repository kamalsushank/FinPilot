import React, { useCallback, useEffect, useState } from "react";

import { Bot, Wallet, Send, RefreshCw, ChevronDown, ChevronUp, ArrowDownLeft, ArrowUpRight, CalendarDays, TrendingUp, CircleDollarSign } from "lucide-react";

import "./styles.css";



const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

const USER_ID = "demo";

const money = (value) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));

const dateLabel = (value) => value ? new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—";

const arrayFrom = (value) => Array.isArray(value) ? value : Array.isArray(value?.items) ? value.items : Array.isArray(value?.results) ? value.results : [];



async function api(path, options = {}) {

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });

  const raw = await response.text();

  let data;

  try { data = raw ? JSON.parse(raw) : null; } catch { data = raw; }

  if (!response.ok) throw new Error(typeof data === "object" ? (data?.detail || JSON.stringify(data)) : (data || `Request failed (${response.status})`));

  return data;

}



function App() {

  const [input, setInput] = useState("");

  const [messages, setMessages] = useState([{ role: "assistant", content: "Hi! Tell me what happened or what you want to know in plain English. For example: ‘I earned ₹5,000 from a project, spent ₹100 on food and ₹200 on clothes.’ I’ll record clear transactions and explain what I did." }]);

  const [busy, setBusy] = useState(false);

  const [health, setHealth] = useState("checking");

  const [refreshing, setRefreshing] = useState(false);

  const [expanded, setExpanded] = useState("overview");

  const [summary, setSummary] = useState({});

  const [transactions, setTransactions] = useState([]);

  const [bills, setBills] = useState([]);

  const [upcoming, setUpcoming] = useState([]);

  const [holdings, setHoldings] = useState([]);

  const [billFormOpen, setBillFormOpen] = useState(false);

  const [billName, setBillName] = useState("");

  const [billAmount, setBillAmount] = useState("");

  const [billDue, setBillDue] = useState("");



  const loadData = useCallback(async () => {

    setRefreshing(true);

    const results = await Promise.allSettled([api("/health"), api("/summary"), api("/transactions?limit=50"), api("/bills"), api("/bills/upcoming?limit=2"), api(`/investments/holdings/${USER_ID}`)]);

    setHealth(results[0].status === "fulfilled" ? "online" : "offline");

    if (results[1].status === "fulfilled") setSummary(results[1].value || {});

    if (results[2].status === "fulfilled") setTransactions(arrayFrom(results[2].value));

    if (results[3].status === "fulfilled") setBills(arrayFrom(results[3].value));

    if (results[4].status === "fulfilled") setUpcoming(arrayFrom(results[4].value));

    if (results[5].status === "fulfilled") setHoldings(arrayFrom(results[5].value));

    setRefreshing(false);

  }, []);



  useEffect(() => { loadData(); }, [loadData]);



  const income = Number(summary.total_income ?? summary.income ?? summary.monthly_income ?? 0);

  const expenses = Number(summary.total_expenses ?? summary.expenses ?? summary.monthly_expenses ?? 0);

  const balance = Number(summary.balance ?? summary.net_balance ?? income - expenses);



  async function sendMessage(event) {

    event?.preventDefault();

    const message = input.trim();

    if (!message || busy) return;

    setMessages((old) => [...old, { role: "user", content: message }]);

    setInput("");

    setBusy(true);

    try {

      const result = await api("/chat", { method: "POST", body: JSON.stringify({ user_id: USER_ID, message }) });

      // The API now returns a human-readable response; do not stringify its full object.

      const answer = typeof result?.response === "string" ? result.response : typeof result?.answer === "string" ? result.answer : "I received a response, but it wasn't in a readable format. Please check the backend response.";

      setMessages((old) => [...old, { role: "assistant", content: answer, sources: Array.isArray(result?.sources) ? result.sources : [], recommendations: Array.isArray(result?.recommendations) ? result.recommendations : [] }]);

      await loadData();

    } catch (error) {

      setMessages((old) => [...old, { role: "assistant", content: `I couldn't reach the backend: ${error.message}. Check that FastAPI is running and VITE_API_BASE_URL points to it.` }]);

    } finally { setBusy(false); }

  }



  async function addBill(event) {

    event.preventDefault();

    try {

      await api("/bills", { method: "POST", body: JSON.stringify({ name: billName, amount: Number(billAmount), due_date: billDue }) });

      setBillName(""); setBillAmount(""); setBillDue(""); setBillFormOpen(false);

      setMessages((old) => [...old, { role: "assistant", content: `I've added ${billName} for ${money(billAmount)}, due ${dateLabel(billDue)}.` }]);

      await loadData();

    } catch (error) { setMessages((old) => [...old, { role: "assistant", content: `I couldn't add that bill: ${error.message}` }]); }

  }



  async function saveRecommendation(item) {

    const amountText = window.prompt(`How much are you investing in ${item.name}? Enter the amount in INR.`);

    if (!amountText) return;

    const amount = Number(amountText.replace(/,/g, ""));

    if (!Number.isFinite(amount) || amount <= 0) { window.alert("Enter a valid positive amount."); return; }

    const frequency = window.prompt("Investment frequency? Enter monthly, yearly, or one-time.", "monthly") || "monthly";

    try {

      await api("/investments/holdings", { method: "POST", body: JSON.stringify({ user_id: USER_ID, product_name: item.name, asset_type: item.type || "Investment", amount, frequency, source_url: item.source_url || "", notes: `Risk: ${item.risk || "Not specified"}. ${item.why_it_may_fit || ""}` }) });

      setMessages((old) => [...old, { role: "assistant", content: `${item.name} has been added to your recorded investments. This records your selection; it does not execute a purchase or create an account with the provider.` }]);

      await loadData();

    } catch (error) { setMessages((old) => [...old, { role: "assistant", content: `I couldn't save this investment: ${error.message}` }]); }

  }



  async function markPaid(id) {

    try {

      await api(`/bills/${id}/pay`, { method: "POST" });

      setMessages((old) => [...old, { role: "assistant", content: `I've marked bill #${id} as paid.` }]);

      await loadData();

    } catch (error) {

      setMessages((old) => [...old, { role: "assistant", content: `I couldn't update that bill: ${error.message}` }]);

    }

  }



  return <div className="app-shell">

    <header className="topbar">

      <div className="brand"><div className="brand-icon"><Wallet size={22} /></div><div><h1>FinPilot</h1><p>Your money, in plain English</p></div></div>

      <div className={`status ${health}`}><span />{health === "online" ? "Connected" : health === "checking" ? "Connecting…" : "Backend offline"}<button onClick={loadData} title="Refresh data" aria-label="Refresh data"><RefreshCw size={16} className={refreshing ? "spin" : ""} /></button></div>

    </header>



    <main className="layout">

      <section className="chat-panel">

        <div className="chat-heading"><div className="bot-icon"><Bot size={22} /></div><div><h2>Money assistant</h2><p>Record activity, ask questions, or explore investments.</p></div></div>

        <div className="examples"><span>Try:</span><button onClick={() => setInput("I earned ₹5,000 from a project, spent ₹100 on food and ₹200 on clothes")}>Record multiple transactions</button><button onClick={() => setInput("Show my financial summary and upcoming bills")}>My finances</button><button onClick={() => setInput("I want to invest ₹500 per month for 10 years. Compare mutual funds, government schemes and life insurance, with sources.")}>Explore investments</button></div>

        <div className="messages" aria-live="polite">

          {messages.map((message, index) => <div key={`${index}-${message.role}`} className={`message ${message.role}`}>

            <div className="message-avatar">{message.role === "assistant" ? <Bot size={17} /> : "You"}</div>

            <div className="message-body"><div className="message-content">{message.content}</div>

              {message.recommendations?.length > 0 && <div className="recommendation-list"><b>Researched options — review before selecting</b>{message.recommendations.map((item, i) => <article className="recommendation-card" key={`${item.name}-${i}`}><div className="recommendation-top"><strong>{item.name}</strong><span>{item.type}</span></div><p>{item.why_it_may_fit}</p><small>Risk: {item.risk} · Minimum: {item.minimum_investment} · Lock-in/liquidity: {item.liquidity_or_lock_in}</small><small>Status: {item.current_status}</small>{item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">Official details</a>}<button type="button" onClick={() => saveRecommendation(item)}>Add to my investments</button></article>)}</div>}

              {message.sources?.length > 0 && <div className="sources"><b>Research sources</b>{message.sources.map((source, i) => <a key={`${source.url}-${i}`} href={source.url} target="_blank" rel="noreferrer">{source.title || source.url}</a>)}</div>}

            </div>

          </div>)}

          {busy && <div className="thinking"><span /> <span /> <span /> Thinking and updating your records…</div>}

        </div>

        <form className="composer" onSubmit={sendMessage}>

          <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(e); } }} placeholder="Tell me what happened, or what you want to know…" rows={2} maxLength={5000} />

          <button type="submit" disabled={!input.trim() || busy} aria-label="Send message"><Send size={18} /></button>

          <small>Enter to send · Shift + Enter for a new line</small>

        </form>

      </section>



      <aside className="data-panel">

        <div className="panel-title"><div><h2>Your finances</h2><p>Updated from your database</p></div><button className="refresh-small" onClick={loadData} aria-label="Refresh finances"><RefreshCw size={15} /></button></div>

        <div className="stat-grid">

          <div className="stat-card"><span><ArrowDownLeft size={16} /> Income</span><strong>{money(income)}</strong></div>

          <div className="stat-card"><span><ArrowUpRight size={16} /> Expenses</span><strong>{money(expenses)}</strong></div>

          <div className="stat-card balance"><span><CircleDollarSign size={16} /> Net balance</span><strong>{money(balance)}</strong></div>

        </div>

        <DataSection title="Upcoming bills" icon={<CalendarDays size={17} />} expanded={expanded === "bills"} onClick={() => setExpanded(expanded === "bills" ? "" : "bills")}>

          <button className="add-bill-toggle" type="button" onClick={() => setBillFormOpen(!billFormOpen)}>＋ Add a bill</button>

          {billFormOpen && <form className="bill-form" onSubmit={addBill}><input value={billName} onChange={e=>setBillName(e.target.value)} placeholder="Bill name (e.g. Electricity)" required/><input type="number" min="1" step="0.01" value={billAmount} onChange={e=>setBillAmount(e.target.value)} placeholder="Amount in ₹" required/><input type="date" value={billDue} onChange={e=>setBillDue(e.target.value)} required/><button type="submit">Save bill</button></form>}

          {upcoming.length ? upcoming.map((bill) => <div className="data-row" key={bill.id}><div><b>{bill.name || "Bill"}</b><small>Due {dateLabel(bill.due_date)}</small></div><div className="row-right"><strong>{money(bill.amount)}</strong>{bill.status !== "paid" && bill.id && <button className="text-button" onClick={() => markPaid(bill.id)}>Mark paid</button>}</div></div>) : <p className="empty">No upcoming unpaid bills recorded.</p>}

          {bills.length > upcoming.length && <p className="subtle">Showing the two nearest unpaid bills.</p>}

        </DataSection>

        <DataSection title={`Recent transactions (${transactions.length})`} icon={<ArrowUpRight size={17} />} expanded={expanded === "transactions"} onClick={() => setExpanded(expanded === "transactions" ? "" : "transactions")}>

          {transactions.length ? transactions.slice(0, 8).map((tx, i) => <div className="data-row" key={tx.id ?? i}><div><b>{tx.description || tx.category || "Transaction"}</b><small>{dateLabel(tx.transaction_date || tx.date)} · {tx.type || tx.transaction_type || ""}</small></div><strong className={(tx.type || tx.transaction_type) === "income" ? "positive" : "negative"}>{(tx.type || tx.transaction_type) === "income" ? "+" : "−"}{money(tx.amount)}</strong></div>) : <p className="empty">Your transactions will appear here when you tell the assistant about them.</p>}

        </DataSection>

        <DataSection title={`My investments (${holdings.length})`} icon={<TrendingUp size={17} />} expanded={expanded === "holdings"} onClick={() => setExpanded(expanded === "holdings" ? "" : "holdings")}>

          {holdings.length ? holdings.map(item => <div className="data-row" key={item.id}><div><b>{item.product_name}</b><small>{item.asset_type} · {item.frequency} · Since {dateLabel(item.start_date)}</small></div><strong>{money(item.amount)}</strong></div>) : <p className="empty">No investments recorded yet. Research options in the assistant and add the ones you actually select.</p>}

        </DataSection>

        <div className="privacy-note"><TrendingUp size={17} /><p>Suggested investments are not holdings. Adding one here records your selection only; it does not execute a purchase. Verify provider details before investing.</p></div>

      </aside>

    </main>

    <footer>FinPilot · Personal finance assistant prototype · Review important financial decisions before acting.</footer>

  </div>;

}



function DataSection({ title, icon, expanded, onClick, children }) {

  return <section className="data-section"><button className="section-toggle" onClick={onClick}>{icon}<span>{title}</span>{expanded ? <ChevronUp size={17} /> : <ChevronDown size={17} />}</button>{expanded && <div className="section-content">{children}</div>}</section>;

}



export default App;
