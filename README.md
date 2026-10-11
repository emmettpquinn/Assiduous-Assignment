# Senus PLC – Board Report

A small Flask web app that turns Senus PLC's published financial documents into an interactive board report for management, the board, equity investors and lenders.

## Run it

```bash
pip install -r requirements.txt
python app.py                      # http://127.0.0.1:5000  – login: ceo@senus.com / boardreport
```

Optional AI features:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # enables AI commentary + "Ask the board report"
python extract.py                    # re-extract all figures from the scanned PDF with Claude
python -m pytest                     # tests
```

## How it works

```
 Source PDF (Euronext)            extract.py                      SQLite            app.py (Flask)
 ┌──────────────────────┐  render page  ┌──────────────┐  save   ┌───────┐  read  ┌──────────────────────┐
 │ Information Document │ ───────────▶ │ Claude vision │ ──────▶ │ facts │ ─────▶ │ metrics.py → charts, │
 │ pp.53–90 = scans     │   to PNG      │ + JSON schema │         └───────┘        │ tables, checks       │
 └──────────────────────┘               └──────────────┘                          │ ai.py → commentary/Q&A│
                                         score vs answer key                       └──────────────────────┘
                                         + accounting checks
```

| File | What it does |
|---|---|
| `extract.py` | Renders each scanned statement page to an image, asks Claude (`claude-opus-5-5`) to read the figures into a Pydantic schema, saves them to SQLite, then scores them against the hand-checked figures and runs accounting checks. |
| `db.py` | One SQLite table: `facts(period, item, value, page, method)`. Seeds from `data/financials.json` on first run. |
| `metrics.py` | Plain functions for every metric, the EBITDA→FCF bridge, and accounting identity checks. |
| `ai.py` | Board commentary (tailored to Board / Management / Equity Investors / Credit Providers) and free-text Q&A. Claude only sees the computed figures, never raw text, so it can't introduce numbers that aren't in the report. Falls back to rule-based commentary with no API key. |
| `app.py` + `templates/` | Login, one dashboard page (Chart.js), source links that open the PDF at the right page. |

## Data

The only public source with full financials is the **Senus PLC Information Document** (Dec 2025, published by Euronext Dublin), saved in `data/sources/`. It contains:

* audited FY2025 consolidated accounts with FY2024 comparatives (scanned images, pp.53–76),
* an unaudited **company-only** balance sheet at 8 December 2025, after the October 2025 €830k raise (pp.77–90),
* product / channel / geography revenue split and customer counts for FY2025 (pp.11–12).

The H1 FY2026 interim results (March 2026) are on the Assiduous investor portal, which is a JavaScript app that couldn't be downloaded from programmatically. Drop that PDF in `data/sources/`, add its pages to `data/financials.json`, and run `extract.py` to include it.

## Metrics shown

* **Growth:** revenue and YoY growth, revenue per employee, customers by channel, product/channel mix, Ireland revenue share, FY2030 revenue implied by the 50% CAGR target.
* **Profitability:** gross, EBITDA, operating and net margin; cost breakdown; admin cost ratio.
* **Cash & liquidity:** EBITDA→free cash flow bridge, monthly burn, cash runway (two scenarios), net working capital, current ratio, debtor days.
* **Solvency:** bank debt, net cash, directors' loans, debt service, DSCR, cash cover of debt service, net assets, debt/equity.
* **Returns:** capital employed, ROCE, ROE, asset turnover.

## Assumptions

* EBITDA = operating loss + depreciation (no amortisation; no intangibles are capitalised).
* Free cash flow = operating cash flow − capex + disposal proceeds.
* Runway at Dec 2025 uses the FY2025 burn (base case) and the 1 Jul–8 Dec 2025 loss rate (downside). The stub loss (€432k in ~5 months) is much higher than the FY2025 rate. H1 is seasonally weak and the period probably includes listing costs, but the documents don't say.
* Dec 2025 figures are company-only, not consolidated, so they aren't strictly comparable with the group FY figures.
* Ratios with negative denominators (ROE, debt/equity with negative equity) are shown as "n/m".
* MoM revenue, bookings and ARR aren't published, so they aren't shown rather than estimated.

## Validating the outputs

1. **Answer key.** `data/financials.json` holds every figure, hand-checked against the page images, with its page number. `extract.py` reports how many AI-extracted figures match it.
2. **Accounting checks.** 13 identities are re-run on every page load: gross profit, operating profit, tax, the cash-flow roll-forward, cash-flow vs balance-sheet cash, and assets − liabilities = net assets for each period. A misread figure shows up as a FAIL on the dashboard.
3. **Cross-checks against management's own numbers.** Growth (21.6%) and gross margin (77.5% vs 62.8%) match the Operating & Financial Review (p.26), and the tests assert this.
4. **Every figure links to its source page** in the "Data & validation" section.

## AI-assisted development workflow

Built with Claude Code. Claude Code found the source document, and since the statements are scanned it rendered the pages and read them visually. It then wrote the code and tests. The figures were checked against the page images and by the accounting checks above. The app also uses Claude at runtime for two things: extracting figures from the scans, and writing commentary and answers from the computed metrics.
