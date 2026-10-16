from datetime import date

from options.core.calendar import NseCalendar
from options.daemon import main, next_start
from tests.options.fixtures import Clock, ist

CAL = NseCalendar()


def test_next_start_before_during_and_after_the_session():
    assert next_start(ist(2026, 10, 16, 7, 0), CAL, None) == ist(2026, 10, 16, 8, 30)
    late = ist(2026, 10, 16, 11, 0)
    assert next_start(late, CAL, None) == late                                # restarted mid-day: run now
    assert next_start(late, CAL, date(2026, 10, 16)) == ist(2026, 10, 19, 8, 30)  # already ran today
    assert next_start(ist(2026, 10, 16, 15, 30), CAL, None) == ist(2026, 10, 19, 8, 30)
    assert next_start(ist(2026, 10, 19, 16, 0), CAL, None) == ist(2026, 10, 21, 8, 30)  # skips Dussehra


def test_main_sleeps_until_the_session_and_runs_it_once_per_day():
    clock = Clock(ist(2026, 10, 16, 6, 0))
    runs = []

    def session():
        runs.append(clock())
        clock.now = clock.now.replace(hour=15, minute=31)                      # a session lasts until the close
        return 0

    main(now_fn=clock, sleep=clock.sleep, session=session, calendar=CAL, max_sessions=2)
    assert runs == [ist(2026, 10, 16, 8, 30), ist(2026, 10, 19, 8, 30)]
