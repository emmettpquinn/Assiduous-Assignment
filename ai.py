"""AI commentary and Q&A over the board report.

Claude only sees the computed figures (not the raw PDF), so every number it quotes comes
from the database. Without ANTHROPIC_API_KEY the app falls back to rule-based commentary.
"""
import os

import anthropic

MODEL = "claude-opus-5-5"

SYSTEM = """You are a CFO-grade analyst writing for the board of Senus PLC, an Irish natural capital software company listed on Euronext Access Dublin.
Use only the figures provided. Do not invent numbers. If something cannot be answered from the figures, say so.
Write in plain English, short paragraphs or bullets, euro amounts rounded sensibly (e.g. €837k)."""


def enabled():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _ask_claude(prompt):
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM,
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        return "The model declined to answer this request."
    return "".join(b.text for b in response.content if b.type == "text")


def commentary(report_text, audience):
    if not enabled():
        return None
    return _ask_claude(
        f"Figures:\n{report_text}\n\nWrite the board report commentary for this audience: {audience}. "
        "Cover: headline performance, profitability, cash and runway, solvency, and the 3 key risks / questions "
        "for the board. Maximum 300 words."
    )


def answer(report_text, question):
    if not enabled():
        return "AI Q&A needs an ANTHROPIC_API_KEY. Set it and restart the app."
    return _ask_claude(f"Figures:\n{report_text}\n\nQuestion: {question}")


def _eur(v):
    return f"-€{-v/1e3:,.0f}k" if v < 0 else f"€{v/1e3:,.0f}k"


def rule_based_commentary(facts):
    """Deterministic fallback so the report always has commentary."""
    fy24, fy25, dec = facts["FY2024"], facts["FY2025"], facts["DEC2025"]
    growth = fy25["revenue"] / fy24["revenue"] - 1
    gm24, gm25 = fy24["gross_profit"] / fy24["revenue"], fy25["gross_profit"] / fy25["revenue"]
    burn = -(fy25["cf_operating"] + fy25["capex"] + fy25["disposal_proceeds"]) / 12
    return "\n".join([
        f"- Revenue grew {growth:.1%} to €{fy25['revenue']/1e3:,.0f}k; gross margin rose from {gm24:.1%} to {gm25:.1%}.",
        f"- Operating loss narrowed {1 - fy25['operating_profit']/fy24['operating_profit']:.0%} to €{-fy25['operating_profit']/1e3:,.0f}k as admin costs fell.",
        f"- Free cash burn was about €{burn/1e3:,.0f}k a month in FY2025. Cash was €{fy25['cash']/1e3:,.0f}k at June 2025, "
        f"rising to €{dec['cash']/1e3:,.0f}k by 8 December 2025 after the equity raise (~{dec['cash']/burn:.0f} months at the FY2025 burn).",
        f"- Net assets moved from {_eur(fy25['net_assets'])} (June 2025) to {_eur(dec['net_assets'])} (December 2025).",
        f"- The company lost €{-dec['profit_after_tax']/1e3:,.0f}k between 1 July and 8 December 2025, faster than the FY2025 rate. Worth asking management why.",
    ])
