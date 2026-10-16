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
    code = session.run(OptionsSettings(DATA_PROVIDER="kite", KITE_API_KEY="", KITE_API_SECRET=""),
                       now_fn=Clock(ist(2026, 10, 16, 8, 30)), sleep=lambda s: None, store=store, notifier=notifier)
    assert code == 2 and "KITE_API_KEY" in notifier.texts()[0]


def test_missing_angel_keys(store):
    notifier = RecordingNotifier()
    cfg = OptionsSettings(DATA_PROVIDER="angel", ANGEL_API_KEY="k", ANGEL_CLIENT_CODE="A123", ANGEL_PIN="",
                          ANGEL_TOTP_SECRET="")
    code = session.run(cfg, now_fn=Clock(ist(2026, 10, 16, 8, 30)), sleep=lambda s: None, store=store,
                       notifier=notifier)
    assert code == 2 and "ANGEL_PIN / ANGEL_TOTP_SECRET are not set" in notifier.texts()[0]


class AutoLoginBroker(FakeBroker):
    """Angel One's shape: logs in by itself, no login link."""
    auto_login = True
    name = "Angel One"

    def __init__(self, fail_times=0):
        super().__init__()
        self.fail_times = fail_times
        self.logins = 0

    def login(self):
        self.logins += 1
        if self.logins <= self.fail_times:
            raise RuntimeError("login refused (AB1050): Invalid totp")
        return "A123"


def test_auto_login_needs_no_prompt(store):
    broker = AutoLoginBroker()
    code, notifier = run(store, Clock(ist(2026, 10, 16, 15, 30, 50)), broker)
    assert code == 0 and broker.logins == 1
    assert not any("Good morning" in t or "Kite" in t for t in notifier.texts())
    assert any("Recording started" in t for t in notifier.texts())
    assert store.load_access_token(TODAY) == "auto-login"         # the dashboard shows "connected"


def test_auto_login_retries_then_records(store):
    broker = AutoLoginBroker(fail_times=2)
    code, notifier = run(store, Clock(ist(2026, 10, 16, 14, 57)), broker)
    texts = notifier.texts()
    assert code == 0 and broker.logins == 3
    assert sum("Retrying" in t for t in texts) == 1 and "Invalid totp" in texts[0]
    assert any("Recording started" in t for t in texts)


def test_auto_login_gives_up_at_the_deadline(store):
    broker = AutoLoginBroker(fail_times=99)
    code, notifier = run(store, Clock(ist(2026, 10, 16, 14, 50)), broker)
    assert code == 1 and broker.logins == 5        # 14:50, 14:50:30, 14:51:30, 14:53:30, 14:58:30; next would pass 15:00
    assert "Angel One login failed" in notifier.texts()[-1] and "AB1050" in notifier.texts()[-1]
