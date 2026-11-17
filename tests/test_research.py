import asyncio

import pytest

from prognozy.research import Researcher, ResearchUnavailable, Source, default_sources
from tests.conftest import binary_question

LONG = "fact " * 100


def _src(name, result=None, exc=None):
    async def fetch(q):
        if exc:
            raise exc
        return result

    return Source(name, fetch)


def test_all_sources_fail_means_skip():
    r = Researcher([_src("a", exc=TimeoutError()), _src("b", exc=ConnectionError())])
    with pytest.raises(ResearchUnavailable):
        asyncio.run(r.run(binary_question()))


def test_too_short_research_means_skip():
    r = Researcher([_src("a", result="nic")], min_chars=200)
    with pytest.raises(ResearchUnavailable):
        asyncio.run(r.run(binary_question()))


def test_no_sources_means_skip():
    with pytest.raises(ResearchUnavailable):
        asyncio.run(Researcher([]).run(binary_question()))


def test_partial_failure_uses_remaining_sources():
    r = Researcher([_src("a", exc=TimeoutError()), _src("b", result=LONG), _src("c", result=LONG)])
    text = asyncio.run(r.run(binary_question()))
    assert "Source: b" in text and "Source: c" in text and "Source: a" not in text


def test_default_sources_follow_keys(monkeypatch):
    assert default_sources() == []
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key-123")
    assert [s.name for s in default_sources()] == ["openrouter/perplexity/sonar-pro"]
    monkeypatch.setenv("ASKNEWS_CLIENT_ID", "id-123456")
    monkeypatch.setenv("ASKNEWS_SECRET", "secret-123456")
    assert [s.name for s in default_sources()][0] == "AskNews"
    assert len(default_sources(("m1", "m2"))) == 3
