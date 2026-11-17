import asyncio

import pytest
from forecasting_tools import ReasonedPrediction

from prognozy import cli
from prognozy.ledger import Ledger
from prognozy.ops import BudgetExceeded, DailyBudget, Healthcheck
from prognozy.runner import run_once
from tests.conftest import FakeMetaculusClient, binary_question
from tests.test_publish_flow import REASONING, FakeBot, _researcher


class FakeResponse:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._data


def test_healthcheck_pings_and_never_raises():
    sent = []
    hc = Healthcheck("https://hc-ping.com/abc/", post=lambda url, **kw: sent.append(url))
    hc.start(); hc.success("ok"); hc.fail("źle")
    assert sent == ["https://hc-ping.com/abc/start", "https://hc-ping.com/abc", "https://hc-ping.com/abc/fail"]

    def broken(url, **kw):
        raise ConnectionError()

    Healthcheck("https://x", post=broken).fail("x")  # nie rzuca
    Healthcheck(None, post=broken).fail("x")  # wyłączony


def test_budget_blocks_when_spent():
    over = DailyBudget(5.0, get=lambda *a, **k: FakeResponse({"data": {"usage_daily": 5.2}}), api_key="k")
    with pytest.raises(BudgetExceeded):
        over.check()
    DailyBudget(5.0, get=lambda *a, **k: FakeResponse({"data": {"usage_daily": 1.0}}), api_key="k").check()


def test_budget_read_failure_or_disabled_does_not_stop_bot():
    DailyBudget(5.0, get=lambda *a, **k: FakeResponse({}, 500), api_key="k").check()
    DailyBudget(None, get=lambda *a, **k: 1 / 0, api_key="k").check()
    DailyBudget(5.0, get=lambda *a, **k: 1 / 0, api_key="").check()


class StopAfter:
    def __init__(self, n):
        self.n = n

    def check(self):
        if self.n <= 0:
            raise BudgetExceeded("limit")
        self.n -= 1


def test_runner_stops_between_batches_when_budget_runs_out(tmp_path):
    client = FakeMetaculusClient({"t": [binary_question(i) for i in range(1, 6)]})
    ledger = Ledger(tmp_path / "r.sqlite")
    summary = asyncio.run(run_once(
        bot=FakeBot(_researcher()), client=client, ledger=ledger, tournaments=["t"],
        dry_run=False, budget=StopAfter(1), batch_size=2,
    ))
    assert summary.budget_stopped and len(client.predictions) == 2
    assert "LIMIT" in summary.one_line()


def test_ensemble_cycles_models_and_names_them_in_comment():
    class Llm:
        def __init__(self, model):
            self.model = model

        async def invoke(self, prompt):
            return "ok"

    bot = FakeBot(_researcher())
    bot._forecasters = [Llm("m1"), Llm("m2")]
    out = [asyncio.run(bot._reason("p")) for _ in range(4)]
    assert [o.split(")")[0] for o in out] == ["(model: m1", "(model: m2"] * 2


def test_run_without_keys_reports_failure_to_healthcheck(monkeypatch):
    sent = []
    monkeypatch.setenv("PROGNOZY_HEALTHCHECK_URL", "https://hc.example/abc")
    monkeypatch.setattr("prognozy.ops.requests.post", lambda url, **kw: sent.append(url))
    assert cli.main(["run", "--mode", "test", "--dry-run"]) == 1
    assert sent == ["https://hc.example/abc/start", "https://hc.example/abc/fail"]


def test_reasoning_unused_import_guard():
    assert ReasonedPrediction and REASONING
