"""Options tests run offline: the session's background fetchers (Yahoo macro quotes, RBI news)
are replaced by quiet stand-ins, so no test depends on, or waits for, the network."""

import pytest


class QuietFetcher:
    def __init__(self, *args, **kwargs):
        pass

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def snapshot(self):
        return None


@pytest.fixture(autouse=True)
def _offline_fetchers(monkeypatch):
    from options import session
    monkeypatch.setattr(session, "MacroFetcher", QuietFetcher)
    monkeypatch.setattr(session, "NewsFetcher", QuietFetcher)
