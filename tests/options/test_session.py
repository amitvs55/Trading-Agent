import pytest

from options import session
from options.config import OptionsSettings
from options.storage import Store, make_engine
from tests.options.fixtures import TODAY, Clock, FakeBroker, RecordingNotifier, ist

CFG = OptionsSettings(KITE_API_KEY="k", KITE_API_SECRET="s", OPTIONS_INDICES=["NIFTY"])


@pytest.fixture
def store(tmp_path):
    return Store(make_engine(f"sqlite:///{tmp_path}/options.db"))


def run(store, clock, broker=None, notifier=None, sleep=None):
    notifier = notifier or RecordingNotifier()
    code = session.run(CFG, now_fn=clock, sleep=sleep or clock.sleep, store=store,
                       notifier=notifier, broker=broker or FakeBroker())
    return code, notifier


def test_non_trading_day_does_nothing(store):
    code, notifier = run(store, Clock(ist(2026, 10, 20, 8, 30)))         # Dussehra
    assert code == 0 and notifier.messages == []


def test_full_session_with_saved_token(store):
    store.save_access_token(TODAY, "good", "AB1234", ist(2026, 10, 16, 8, 35))
    broker = FakeBroker()
    code, notifier = run(store, Clock(ist(2026, 10, 16, 15, 30, 50)), broker)
    assert code == 0
    assert broker.token == "good"
    texts = notifier.texts()
    assert any("Recording started" in t and "lot 65" in t and "strike step 50" in t for t in texts)
    assert "Recording summary" in texts[-1]
    assert broker.ticker_obj.stopped


def login_at(store, clock, when, token="good"):
    """sleep() that advances the clock and saves a token once `when` is reached."""
    done = {"saved": False}

    def sleep(seconds):
        clock.sleep(seconds)
        if not done["saved"] and clock() >= when:
            store.save_access_token(TODAY, token, "AB1234", clock())
            done["saved"] = True
    return sleep


def test_login_prompt_reminders_and_wait(store):
    clock = Clock(ist(2026, 10, 16, 9, 0))
    code, notifier = run(store, clock, sleep=login_at(store, clock, ist(2026, 10, 16, 9, 6)))
    texts = notifier.texts()
    assert code == 0
    assert "Good morning" in texts[0] and notifier.messages[0][1] == [("Login to Kite", FakeBroker.LOGIN_URL)]
    assert sum("Still waiting" in t for t in texts) == 1                  # only the 09:05 reminder


def test_no_login_by_the_deadline(store):
    code, notifier = run(store, Clock(ist(2026, 10, 16, 14, 59, 30)))
    assert code == 1
    assert "Good morning" in notifier.texts()[0]
    assert "No Kite login by 15:00" in notifier.texts()[-1]


def test_rejected_token_triggers_a_new_login(store):
    store.save_access_token(TODAY, "stale", "AB1234", ist(2026, 10, 16, 8, 31))
    clock = Clock(ist(2026, 10, 16, 14, 58))
    broker = FakeBroker(bad_tokens={"stale"})
    code, notifier = run(store, clock, broker, sleep=login_at(store, clock, clock(), token="fresh"))
    assert code == 0 and broker.token == "fresh"
    assert any("Good morning" in t for t in notifier.texts())


def test_missing_kite_keys(store):
    notifier = RecordingNotifier()
    code = session.run(OptionsSettings(KITE_API_KEY="", KITE_API_SECRET=""), now_fn=Clock(ist(2026, 10, 16, 8, 30)),
                       sleep=lambda s: None, store=store, notifier=notifier)
    assert code == 2 and "KITE_API_KEY" in notifier.texts()[0]
