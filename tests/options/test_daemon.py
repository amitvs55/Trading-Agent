from datetime import date, datetime, timedelta

import pytest

from options.admin.repo import AdminRepo
from options.core.calendar import NseCalendar
from options.daemon import COMMAND_KEY, STATUS_KEY, Supervisor, can_start_now, next_start
from options.storage import make_engine
from tests.options.fixtures import Clock, ist

CAL = NseCalendar()


def test_next_start_before_during_and_after_the_session():
    assert next_start(ist(2026, 10, 16, 7, 0), CAL, None) == ist(2026, 10, 16, 8, 30)
    late = ist(2026, 10, 16, 11, 0)
    assert next_start(late, CAL, None) == late                                # restarted mid-day: run now
    assert next_start(late, CAL, date(2026, 10, 16)) == ist(2026, 10, 19, 8, 30)  # already ran today
    assert next_start(ist(2026, 10, 16, 15, 30), CAL, None) == ist(2026, 10, 19, 8, 30)
    assert next_start(ist(2026, 10, 19, 16, 0), CAL, None) == ist(2026, 10, 21, 8, 30)  # skips Dussehra
    assert can_start_now(ist(2026, 10, 16, 14, 59), CAL) and not can_start_now(ist(2026, 10, 16, 15, 1), CAL)


class FakeProcess:
    def __init__(self):
        self.code: int | None = None
        self.terminated = False

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated = True
        self.code = -15

    def wait(self, timeout=None):
        return self.code

    def kill(self):
        self.code = -9


@pytest.fixture
def setup(tmp_path):
    repo = AdminRepo(make_engine(f"sqlite:///{tmp_path}/d.db"), secret_key="k")
    clock = Clock(ist(2026, 10, 16, 6, 0))
    spawned: list[FakeProcess] = []

    def spawn():
        spawned.append(FakeProcess())
        return spawned[-1]

    return Supervisor(repo, spawn=spawn, now_fn=clock, calendar=CAL), repo, clock, spawned


def test_waits_then_runs_the_session_once_per_day(setup):
    sup, repo, clock, spawned = setup
    sup.step(clock())
    assert spawned == [] and repo.get_meta_json(STATUS_KEY)["state"] == "waiting"
    assert repo.get_meta_json(STATUS_KEY)["next_start"] == ist(2026, 10, 16, 8, 30).isoformat()

    clock.now = ist(2026, 10, 16, 8, 30, 5)
    sup.step(clock())
    assert len(spawned) == 1 and repo.get_meta_json(STATUS_KEY)["state"] == "running"

    clock.now = ist(2026, 10, 16, 15, 31)
    spawned[0].code = 0                                                     # the session exits after the close
    sup.step(clock())
    sup.step(clock())
    status = repo.get_meta_json(STATUS_KEY)
    assert len(spawned) == 1 and status["state"] == "waiting" and status["last_exit_code"] == 0
    assert status["next_start"] == ist(2026, 10, 19, 8, 30).isoformat()


def test_restart_command_from_the_ui(setup):
    sup, repo, clock, spawned = setup
    clock.now = ist(2026, 10, 16, 10, 0)
    sup.step(clock())                                                       # mid-day start-up runs a session
    assert len(spawned) == 1

    repo.set_meta_json(COMMAND_KEY, {"action": "restart", "requested_at": clock().isoformat(), "by": "admin"})
    clock.now += timedelta(seconds=15)
    sup.step(clock())
    assert spawned[0].terminated and len(spawned) == 2
    assert "restarted" in repo.get_meta_json(STATUS_KEY)["last_command"]

    sup.step(clock())                                                       # the same command isn't applied twice
    assert len(spawned) == 2


def test_restart_after_hours_is_ignored(setup):
    sup, repo, clock, spawned = setup
    clock.now = ist(2026, 10, 16, 16, 0)
    repo.set_meta_json(COMMAND_KEY, {"action": "restart", "requested_at": clock().isoformat()})
    sup.step(clock())
    assert spawned == [] and "ignored" in repo.get_meta_json(STATUS_KEY)["last_command"]


def test_crashed_session_is_not_rerun_the_same_day(setup):
    sup, repo, clock, spawned = setup
    clock.now = ist(2026, 10, 16, 9, 0)
    sup.step(clock())
    spawned[0].code = 1
    clock.now += timedelta(minutes=5)
    sup.step(clock())
    assert len(spawned) == 1 and repo.get_meta_json(STATUS_KEY)["last_exit_code"] == 1


def test_scheduling_survives_without_a_database():
    clock = Clock(ist(2026, 10, 16, 8, 30, 1))
    spawned = []
    sup = Supervisor(None, spawn=lambda: spawned.append(FakeProcess()) or spawned[-1], now_fn=clock, calendar=CAL)
    sup.run(sleep=clock.sleep, steps=2)
    assert len(spawned) == 1
    assert isinstance(sup.session_started_at, datetime)
