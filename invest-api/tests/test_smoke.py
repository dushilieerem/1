"""API smoke tests.  Run: conda run -n svquant python -m pytest tests -q"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("INVEST_DB", str(tmp_path / "invest-test.db"))
    monkeypatch.delenv("INVEST_RESEED", raising=False)
    seed = importlib.import_module("seed")
    importlib.reload(seed)
    appmod = importlib.import_module("app")
    importlib.reload(appmod)

    from fastapi.testclient import TestClient
    client = TestClient(appmod.app)

    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.post("/api/auth/login", json={"username": "demo", "password": "demo1234"})
    assert r.status_code == 200, r.text
    assert r.headers.get("cache-control") == "no-store"
    assert r.headers.get("x-content-type-options") == "nosniff"
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/auth/register", json={"username": "newuser", "password": "password123"})
    assert r.status_code == 400
    assert "不开放注册" in r.json()["detail"]

    r = client.post("/api/auth/sso", json={"token": "fake"})
    assert r.status_code == 401

    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["user"]["username"] == "demo"

    r = client.get("/api/invest/home", headers=headers)
    assert r.status_code == 200, r.text
    home = r.json()
    assert home["isDemo"] is True
    assert len(home["daily"]) == 3
    assert home["review"]["summary"].startswith("沪深 300 ETF")

    r = client.get("/api/invest/data-quality", headers=headers)
    assert r.status_code == 200, r.text
    quality = r.json()
    assert quality["ok"] is True, quality
    assert quality["stocks"] >= 8
    assert {c["key"] for c in quality["checks"]} == {"bars", "financials", "valuations", "etf", "freshness"}

    r = client.get("/api/invest/stock/300750?period=daily")
    assert r.status_code == 200, r.text
    stock = r.json()
    assert stock["quote"]["code"] == "300750"
    assert len(stock["chart"]["bars"]) > 60
    assert stock["valuation"]["pe"] is not None

    r = client.get("/api/invest/topic/ai")
    assert r.status_code == 200
    topic = r.json()
    assert topic["baseRate"]["sample"] > 0
    assert topic["isDemo"] is True
    assert topic["newsIsDemo"] is True

    r = client.get("/api/invest/news")
    assert r.status_code == 200
    news = r.json()
    assert news["isDemo"] is True
    assert len(news["items"]) >= 1

    r = client.get("/api/invest/portfolio", headers=headers)
    assert r.status_code == 200, r.text
    pf = r.json()
    assert pf["riskScore"] > 0
    assert len(pf["diagnosis"]) >= 1
    assert len(pf["holdings"]) == 5

    r = client.get("/api/invest/search?q=%E5%AE%81%E5%BE%B7")
    assert r.status_code == 200
    assert any(x["name"] == "宁德时代" for x in r.json()["results"])

    r = client.get("/api/invest/account/export", headers=headers)
    assert r.status_code == 200
    assert "watchlist" in r.json()
    assert "authEvents" in r.json()
    assert any(e["action"] == "login" for e in r.json()["authEvents"])

    import sqlite3
    audit = sqlite3.connect(appmod.DB_PATH)
    actions = {row[0] for row in audit.execute("SELECT action FROM auth_events")}
    audit.close()
    assert {"login", "export"} <= actions

    r = client.delete("/api/invest/account/data", headers=headers)
    assert r.status_code == 200
    r = client.get("/api/invest/portfolio", headers=headers)
    assert r.status_code == 200
    assert r.json()["holdings"] == []
