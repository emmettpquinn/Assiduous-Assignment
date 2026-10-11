"""Financial metrics for the board report, computed from the facts table.

Every metric is a dict: {name, values: {period: number|None}, fmt, note}.
fmt is one of: eur, pct, x (multiple), months, days.
"""

YEARS = ["FY2024", "FY2025"]
ALL = ["FY2024", "FY2025", "DEC2025"]
STUB_DAYS = 161  # 1 Jul 2025 – 8 Dec 2025


def _div(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def metric(name, values, fmt, note=""):
    return {"name": name, "values": values, "fmt": fmt, "note": note}


def ebitda(f):
    if "operating_profit" not in f or "depreciation" not in f:
        return None
    return f["operating_profit"] + f["depreciation"]


def free_cash_flow(f):
    if "cf_operating" not in f:
        return None
    return f["cf_operating"] + f.get("capex", 0) + f.get("disposal_proceeds", 0)


def capital_employed(f):
    """Total assets less current liabilities."""
    keys = ("tangible_assets", "debtors", "cash", "creditors_within_one_year")
    if not all(k in f for k in keys):
        return None
    return f["tangible_assets"] + f["debtors"] + f["cash"] - f["creditors_within_one_year"]


def growth(facts, segments):
    fy24, fy25 = facts["FY2024"], facts["FY2025"]
    target_fy30 = fy25["revenue"] * 1.5 ** 5
    return [
        metric("Revenue", {p: facts[p].get("revenue") for p in YEARS}, "eur"),
        metric("Revenue growth (YoY)", {"FY2025": fy25["revenue"] / fy24["revenue"] - 1}, "pct"),
        metric("Revenue per employee", {p: _div(facts[p].get("revenue"), facts[p].get("employees")) for p in YEARS}, "eur",
               "Average monthly headcount incl. directors"),
        metric("Customer accounts", {"FY2025": segments["total_customers"]}, "x",
               "36 Enterprise, 98 Independent, 4 R&D"),
        metric("Revenue from Ireland", {p: v for p, v in segments["ireland_share"].items()}, "pct",
               "FY2024 is an upper bound ('less than 5% outside Ireland'). Target is under 50% by FY2030"),
        metric("FY2030 revenue implied by 50% CAGR target", {"FY2025": target_fy30}, "eur",
               "Senus 2030 strategy: at least 50% compound annual growth from the FY2025 base"),
    ]


def profitability(facts):
    def margin(item):
        return {p: _div(facts[p].get(item), facts[p].get("revenue")) for p in YEARS}

    ebitda_v = {p: ebitda(facts[p]) for p in YEARS}
    return [
        metric("Gross margin", margin("gross_profit"), "pct"),
        metric("EBITDA", ebitda_v, "eur", "Operating loss + depreciation"),
        metric("EBITDA margin", {p: _div(ebitda_v[p], facts[p]["revenue"]) for p in YEARS}, "pct",
               "Company targets EBITDA break-even during FY2028"),
        metric("Operating margin", margin("operating_profit"), "pct"),
        metric("Net margin", margin("profit_after_tax"), "pct"),
        metric("Admin expenses / revenue", {p: _div(-facts[p]["admin_expenses"], facts[p]["revenue"]) for p in YEARS}, "pct",
               "Admin expenses are mostly staff costs"),
    ]


def cost_breakdown(facts):
    """Costs as positive numbers, for a stacked chart."""
    return {
        p: {
            "Cost of sales": -facts[p]["cost_of_sales"],
            "Administrative": -facts[p]["admin_expenses"],
            "Distribution": -facts[p]["distribution_costs"],
        }
        for p in YEARS
    }


def fcf_bridge(f):
    """EBITDA -> free cash flow, as (label, amount) steps. Working capital is the balancing item."""
    e, fcf = ebitda(f), free_cash_flow(f)
    interest, tax = f.get("interest_paid", 0), f.get("tax_paid", 0)
    capex = f.get("capex", 0) + f.get("disposal_proceeds", 0)
    working_capital = f["cf_operating"] - e - interest - tax
    return [
        ("EBITDA", e),
        ("Working capital & other", working_capital),
        ("Interest", interest),
        ("Tax (net)", tax),
        ("Capex (net)", capex),
        ("Free cash flow", fcf),
    ]


def cash(facts):
    fcf = {p: free_cash_flow(facts[p]) for p in YEARS}
    burn_fy25 = -fcf["FY2025"] / 12
    stub_burn = -facts["DEC2025"]["profit_after_tax"] / STUB_DAYS * 365 / 12
    return [
        metric("Cash", {p: facts[p].get("cash") for p in ALL}, "eur",
               "Dec 2025 cash is after the €830k October 2025 raise"),
        metric("Free cash flow", fcf, "eur", "Operating cash flow less net capex"),
        metric("Monthly cash burn", {p: _div(-fcf[p], 12) for p in YEARS}, "eur"),
        metric("Cash runway", {
            "FY2024": _div(facts["FY2024"]["cash"], -fcf["FY2024"] / 12),
            "FY2025": _div(facts["FY2025"]["cash"], burn_fy25),
            "DEC2025": _div(facts["DEC2025"]["cash"], burn_fy25),
        }, "months", "Cash ÷ FY2025 monthly FCF burn. Dec 2025 uses the FY2025 burn rate"),
        metric("Runway at stub-period loss rate", {"DEC2025": _div(facts["DEC2025"]["cash"], stub_burn)}, "months",
               f"Dec 2025 cash ÷ monthly loss in 1 Jul–8 Dec 2025 (€{stub_burn:,.0f}/month). "
               "H1 is seasonally weak and likely includes listing costs, so this is a downside case"),
        metric("Net working capital", {p: _nwc(facts[p]) for p in ALL}, "eur",
               "Debtors + cash − creditors due within one year"),
        metric("Current ratio", {p: _div(facts[p]["debtors"] + facts[p]["cash"], facts[p]["creditors_within_one_year"]) for p in ALL}, "x"),
        metric("Debtor days (DSO)", {p: _div(facts[p]["trade_debtors"] * 365, facts[p]["revenue"]) for p in YEARS}, "days"),
    ]


def _nwc(f):
    return f["debtors"] + f["cash"] - f["creditors_within_one_year"]


def solvency(facts):
    out = []
    debt = {p: facts[p].get("bank_loans", 0) for p in ALL}
    out.append(metric("Bank debt", debt, "eur", "€100k SBCI-backed term loan drawn in FY2025"))
    out.append(metric("Net debt / (net cash)", {p: debt[p] - facts[p]["cash"] for p in ALL}, "eur",
                      "Negative = net cash"))
    out.append(metric("Directors' loans", {"FY2025": facts["FY2025"].get("directors_loans")}, "eur",
                      "Repayable to directors at 30 June 2025; not shown at Dec 2025"))
    service = {p: -(facts[p].get("interest_paid", 0) + facts[p].get("loan_repayments", 0)) for p in YEARS}
    out.append(metric("Debt service (interest + principal)", service, "eur"))
    out.append(metric("DSCR (EBITDA / debt service)", {p: _div(ebitda(facts[p]), service[p]) for p in YEARS}, "x",
                      "Negative: debt service is met from cash reserves and equity, not earnings"))
    out.append(metric("Cash / annual debt service", {p: _div(facts[p]["cash"], service[p]) for p in YEARS}, "x",
                      "Liquidity cover — more meaningful than DSCR while EBITDA is negative"))
    out.append(metric("Net assets", {p: facts[p]["net_assets"] for p in ALL}, "eur",
                      "Turned positive again after the October 2025 equity raise"))
    out.append(metric("Debt / equity", {p: _div(debt[p], facts[p]["net_assets"]) if facts[p]["net_assets"] > 0 else None for p in ALL}, "x",
                      "Not meaningful when equity is negative (FY2025)"))
    return out


def returns(facts):
    ce = {p: capital_employed(facts[p]) for p in ALL}
    return [
        metric("Capital employed", ce, "eur", "Total assets less current liabilities"),
        metric("ROCE", {p: _div(facts[p]["operating_profit"], ce[p]) for p in YEARS}, "pct",
               "Operating profit ÷ capital employed. Deeply negative while loss-making"),
        metric("Return on equity", {p: _div(facts[p]["profit_after_tax"], facts[p]["net_assets"]) if facts[p]["net_assets"] > 0 else None for p in YEARS}, "pct",
               "Not meaningful in FY2025 (negative equity)"),
        metric("Asset turnover", {p: _div(facts[p]["revenue"], facts[p]["tangible_assets"] + facts[p]["debtors"] + facts[p]["cash"]) for p in YEARS}, "x"),
    ]


def checks(facts):
    """Accounting identities used to validate extracted figures. Returns (description, ok, diff)."""
    out = []
    for p in YEARS:
        f = facts[p]
        tests = [
            ("Revenue + cost of sales = gross profit", f["revenue"] + f["cost_of_sales"], f["gross_profit"]),
            ("Gross profit − overheads = operating profit",
             f["gross_profit"] + f["distribution_costs"] + f["admin_expenses"] + f["other_operating_income"], f["operating_profit"]),
            ("Loss before tax + tax = loss after tax", f["profit_before_tax"] + f["tax"], f["profit_after_tax"]),
            ("Opening cash + cash flows = closing cash",
             f["cash_beginning"] + f["cf_operating"] + f["cf_investing"] + f["cf_financing"], f["cash_end"]),
            ("Cash flow closing cash = balance sheet cash", f["cash_end"], f["cash"]),
            ("Assets − liabilities = net assets",
             capital_employed(f) - f["creditors_after_one_year"], f["net_assets"]),
        ]
        out += [(f"{p}: {d}", abs(a - b) <= 1, a - b) for d, a, b in tests]
    d = facts["DEC2025"]
    out.append(("DEC2025: Assets − liabilities = net assets",
                abs(capital_employed(d) + 3 - d["creditors_after_one_year"] - d["net_assets"]) <= 1,  # +3 = investments
                capital_employed(d) + 3 - d["creditors_after_one_year"] - d["net_assets"]))
    return out


def build_report(facts, segments):
    return {
        "Growth & Revenue": growth(facts, segments),
        "Profitability": profitability(facts),
        "Cash & Liquidity": cash(facts),
        "Solvency & Leverage": solvency(facts),
        "Returns": returns(facts),
    }
