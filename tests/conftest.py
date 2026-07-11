"""Shared fixtures: network isolation, cache resets, fake LLM clients."""

import json
from pathlib import Path
from typing import Any

import pytest

import src.drug_interactions as di

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hard-fail any accidental real HTTP call from the code under test."""

    def _blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(f"Blocked network call in offline test suite: {args} {kwargs}")

    monkeypatch.setattr("requests.get", _blocked)
    monkeypatch.setattr("requests.post", _blocked)
    monkeypatch.setattr("requests.Session.request", _blocked)
    try:
        import httpx

        monkeypatch.setattr(httpx.Client, "send", _blocked)
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def reset_caches() -> None:
    """Isolate module-level caches between tests."""
    di.reset_caches()
    yield
    di.reset_caches()


@pytest.fixture
def beers_data() -> list[dict]:
    return json.loads((DATA_DIR / "beers_criteria.json").read_text(encoding="utf-8"))


@pytest.fixture
def stopp_start_data() -> dict:
    return json.loads((DATA_DIR / "stopp_start.json").read_text(encoding="utf-8"))


@pytest.fixture
def ddi_data() -> list[dict]:
    return json.loads((DATA_DIR / "drug_interactions.json").read_text(encoding="utf-8"))


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class FakeOpenAI:
    """Stand-in for openai.OpenAI returning a canned completion.

    Instantiate via the ``fake_openai`` fixture factory and monkeypatch it
    over the target module's ``OpenAI`` symbol.
    """

    canned_content: str = "{}"
    last_kwargs: dict | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.init_kwargs = kwargs

        outer = type(self)

        class _Completions:
            @staticmethod
            def create(**kw: Any) -> _FakeResponse:
                outer.last_kwargs = kw
                return _FakeResponse(outer.canned_content)

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


@pytest.fixture
def fake_openai() -> type[FakeOpenAI]:
    """Factory: set ``fake_openai.canned_content`` then monkeypatch the class.

    Example::

        fake_openai.canned_content = '{"overall_risk_score": "high"}'
        monkeypatch.setattr("src.report_generator.OpenAI", fake_openai)
    """

    class _Fresh(FakeOpenAI):
        canned_content = "{}"
        last_kwargs = None

    return _Fresh
