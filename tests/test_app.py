import pytest

import db
import metrics
from app import app


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")


def facts():
    return db.get_facts()[0]


def test_accounting_checks_pass_on_seed_data():
    failures = [c for c in metrics.checks(facts()) if not c[1]]
    assert failures == []


def test_key_metrics_match_published_figures():
    f = facts()
    # Information Document p26: revenue +21.6%, gross margin 77.5% (from 62.8%)
    assert round(f["FY2025"]["revenue"] / f["FY2024"]["revenue"] - 1, 3) == 0.216
    assert round(f["FY2025"]["gross_profit"] / f["FY2025"]["revenue"], 3) == 0.775
    assert round(f["FY2024"]["gross_profit"] / f["FY2024"]["revenue"], 3) == 0.628
    assert metrics.ebitda(f["FY2025"]) == -633694 + 20381


def test_fcf_bridge_adds_up():
    bridge = metrics.fcf_bridge(facts()["FY2025"])
    steps = sum(v for _, v in bridge[:-1])
    assert steps == pytest.approx(bridge[-1][1])


def test_wrong_figure_fails_a_check():
    f = facts()
    f["FY2025"]["gross_profit"] += 1000
    assert any(not ok for _, ok, _ in metrics.checks(f))


def test_dashboard_requires_login():
    client = app.test_client()
    assert client.get("/").status_code == 302
    client.post("/login", data={"email": "ceo@senus.com", "password": "boardreport"})
    assert client.get("/").status_code == 200
