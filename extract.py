"""AI extraction: scanned financial statement pages -> structured figures -> SQLite.

The statements in the Senus Information Document (pages 53-90) are scanned images with no
text layer, so each page is rendered to PNG and read by Claude (vision) with a structured
output schema. Results are saved with method='ai', then checked two ways:
  1. against the hand-verified figures in data/financials.json (accuracy score)
  2. against accounting identities (metrics.checks) - these need no answer key.

Usage:  ANTHROPIC_API_KEY=... python extract.py [--dry-run]
"""
import base64
import sys
from collections import defaultdict
from typing import List, Literal

import anthropic
import pymupdf
from pydantic import BaseModel

import db
import metrics

PDF = db.ROOT / "data" / "sources" / "senus-information-document-2025.pdf"
MODEL = "claude-opus-5-5"

PERIOD_HELP = {
    "FY2024": "financial year ended 30 June 2024 (the comparative column)",
    "FY2025": "financial year ended 30 June 2025",
    "DEC2025": "as at / period ended 8 December 2025",
}


class Fact(BaseModel):
    period: Literal["FY2024", "FY2025", "DEC2025"]
    item: str
    value: float
    label_on_page: str


class PageFacts(BaseModel):
    facts: List[Fact]


def page_png(doc, page_no, dpi=150):
    pix = doc[page_no - 1].get_pixmap(dpi=dpi)
    return base64.b64encode(pix.tobytes("png")).decode()


def targets_by_page():
    """Which items to look for on each page, taken from the seed file's page references."""
    pages = defaultdict(lambda: defaultdict(list))
    for period, items in db.load_seed()["facts"].items():
        for item, (_, page) in items.items():
            pages[page][item].append(period)
    return pages


def extract_page(client, doc, page_no, wanted):
    items = "\n".join(f"- {item} (periods: {', '.join(periods)})" for item, periods in wanted.items())
    periods = "\n".join(f"- {k}: {v}" for k, v in PERIOD_HELP.items())
    prompt = f"""This is page {page_no} of Senus PLC's (formerly ADF Farm Solutions Limited) financial statements, amounts in EUR.

Extract these items:
{items}

Period codes:
{periods}

Rules:
- Use the number exactly as printed. Bracketed numbers are negative; '-' means 0.
- Keep the sign as presented: costs, losses and cash outflows in brackets are negative.
- Balance sheet balances (assets, creditors, loans) are positive. Net assets keep their sign.
- 'tax_paid' is net tax cash flow (tax paid plus tax repaid). 'bank_loans' is total loans.
- 'employees' is the average monthly number of employees.
- Only return items you can actually see on this page. Do not calculate values that are not printed."""

    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": page_png(doc, page_no)}},
                {"type": "text", "text": prompt},
            ],
        }],
        output_format=PageFacts,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        print(f"  page {page_no}: no usable output ({response.stop_reason})")
        return []
    return [f for f in response.parsed_output.facts if f.item in wanted]


def score(extracted):
    """Compare AI output to the hand-verified seed."""
    seed = db.load_seed()["facts"]
    expected = {(p, i): v for p, items in seed.items() for i, (v, _) in items.items()}
    got = {(f.period, f.item): f.value for f in extracted}
    correct = [k for k, v in expected.items() if k in got and abs(got[k] - v) < 0.5]
    wrong = [(k, got[k], expected[k]) for k in expected if k in got and k not in correct]
    missing = [k for k in expected if k not in got]
    return correct, wrong, missing, len(expected)


def main(dry_run=False):
    client = anthropic.Anthropic()
    doc = pymupdf.open(PDF)
    extracted = []
    for page_no, wanted in sorted(targets_by_page().items()):
        if page_no < 53:  # text pages (segment tables) are kept in the seed file
            continue
        facts = extract_page(client, doc, page_no, wanted)
        print(f"page {page_no}: {len(facts)} figures")
        extracted += facts

    correct, wrong, missing, total = score(extracted)
    print(f"\nAccuracy vs hand-verified figures: {len(correct)}/{total} correct")
    for (p, i), got, exp in wrong:
        print(f"  WRONG   {p} {i}: got {got:,.0f}, expected {exp:,.0f}")
    for p, i in missing:
        print(f"  MISSING {p} {i}")

    if dry_run:
        return
    pages = {(p, i): pg for p, items in db.load_seed()["facts"].items() for i, (_, pg) in items.items()}
    db.save_facts([(f.period, f.item, f.value, pages[(f.period, f.item)]) for f in extracted], method="ai")

    facts, _ = db.get_facts()
    print("\nAccounting checks on stored figures:")
    for desc, ok, diff in metrics.checks(facts):
        print(f"  {'PASS' if ok else 'FAIL'}  {desc}" + ("" if ok else f" (off by {diff:,.0f})"))


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
