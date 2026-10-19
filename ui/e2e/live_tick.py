"""Publish live index levels into the e2e database, as the recorder does (ui/e2e/live.spec.ts).

    python ui/e2e/live_tick.py <sqlite path> <nifty> <sensex>

The levels are stamped with the current time, like a tick that has just arrived. Refuses
anything but a local SQLite file.
"""

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from options.core.calendar import IST  # noqa: E402
from options.storage import Store, make_engine  # noqa: E402

PREV = {"NIFTY 50": 23010.20, "SENSEX": 75261.80, "NIFTY FUT": 23040.0}


def publish(db_path: str, nifty: float, sensex: float) -> None:
    store = Store(make_engine(f"sqlite:///{Path(db_path).resolve().as_posix()}"))
    now = datetime.now(IST)
    ms = int(now.timestamp() * 1000)
    levels = {"NIFTY 50": nifty, "SENSEX": sensex, "NIFTY FUT": round(nifty + 25, 2)}
    store.publish_live({"v": 1, "seq": ms, "session": now.date().isoformat(), "sent_ms": ms,
                        "items": [{"symbol": s, "ltp": v, "ts": ms - 150, "prev_close": PREV[s], "prev_source": "quote"}
                                  for s, v in levels.items()]}, now)


if __name__ == "__main__":
    if len(sys.argv) != 4 or not sys.argv[1].endswith(".db"):
        sys.exit("usage: live_tick.py <file.db> <nifty> <sensex>")
    publish(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]))
    print(int(datetime.now(IST).timestamp() * 1000))          # when the level was saved
