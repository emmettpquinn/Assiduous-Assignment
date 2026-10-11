"""Senus PLC board report - Flask app."""
import os
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import ai
import db
import metrics

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

# Single demo login. Set APP_USER / APP_PASSWORD in the environment for anything real.
USERS = {
    os.environ.get("APP_USER", "ceo@senus.com"): generate_password_hash(os.environ.get("APP_PASSWORD", "boardreport")),
}

AUDIENCES = ["Board", "Management", "Equity Investors", "Credit Providers"]


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


@app.template_filter("fmt")
def fmt(value, kind):
    if value is None:
        return "n/m"
    if kind == "eur":
        return f"-€{abs(value)/1e3:,.0f}k" if value < 0 else f"€{value/1e3:,.0f}k"
    if kind == "pct":
        return f"{value:.1%}"
    if kind == "months":
        return f"{value:.1f} mo"
    if kind == "days":
        return f"{value:.0f} days"
    return f"{value:,.1f}x" if abs(value) < 1000 and value != int(value) else f"{value:,.0f}"


def load():
    facts, sources = db.get_facts()
    seed = db.load_seed()
    report = metrics.build_report(facts, seed["segments_fy2025"])
    return facts, sources, seed, report


def report_as_text(report, seed):
    lines = []
    for section, items in report.items():
        lines.append(f"## {section}")
        for m in items:
            vals = ", ".join(f"{p}: {fmt(v, m['fmt'])}" for p, v in m["values"].items())
            lines.append(f"- {m['name']}: {vals}" + (f" ({m['note']})" if m["note"] else ""))
    lines.append("## FY2025 segments")
    lines.append(f"- Revenue by product: {seed['segments_fy2025']['by_product']}")
    lines.append(f"- Revenue by channel: {seed['segments_fy2025']['by_channel']}")
    lines.append("## Company targets")
    lines += [f"- {t}" for t in seed["targets"]]
    return "\n".join(lines)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email, password = request.form.get("email", ""), request.form.get("password", "")
        if email in USERS and check_password_hash(USERS[email], password):
            session["user"] = email
            return redirect(url_for("dashboard"))
        error = "Incorrect email or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    facts, sources, seed, report = load()
    seg = seed["segments_fy2025"]
    charts = {
        "revenue": [facts[p]["revenue"] for p in metrics.YEARS],
        "gross_margin": [round(facts[p]["gross_profit"] / facts[p]["revenue"] * 100, 1) for p in metrics.YEARS],
        "costs": metrics.cost_breakdown(facts),
        "bridge": metrics.fcf_bridge(facts["FY2025"]),
        "cash": {"30 Jun 23": facts["FY2024"]["cash_beginning"], "30 Jun 24": facts["FY2024"]["cash"],
                 "30 Jun 25": facts["FY2025"]["cash"], "8 Dec 25": facts["DEC2025"]["cash"]},
        "by_product": seg["by_product"],
        "by_channel": seg["by_channel"],
    }
    return render_template(
        "dashboard.html",
        user=session["user"],
        report=report,
        charts=charts,
        checks=metrics.checks(facts),
        sources=sorted(sources.items()),
        facts=facts,
        seed=seed,
        fallback=ai.rule_based_commentary(facts),
        ai_enabled=ai.enabled(),
        audiences=AUDIENCES,
    )


@app.post("/api/commentary")
@login_required
def api_commentary():
    _, _, seed, report = load()
    audience = request.json.get("audience", "Board")
    text = ai.commentary(report_as_text(report, seed), audience)
    return jsonify(text=text)


@app.post("/api/ask")
@login_required
def api_ask():
    _, _, seed, report = load()
    question = (request.json.get("question") or "").strip()[:500]
    if not question:
        return jsonify(text="Please type a question.")
    return jsonify(text=ai.answer(report_as_text(report, seed), question))


@app.route("/source")
@login_required
def source_pdf():
    return send_file(db.ROOT / "data" / "sources" / "senus-information-document-2025.pdf")


if __name__ == "__main__":
    app.run(debug=True)
