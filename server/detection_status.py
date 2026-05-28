import threading
from datetime import datetime


class DetectionStatus:
    """Estado thread-safe compartilhado entre o detector e o Flask."""

    def __init__(self):
        self._lock = threading.Lock()
        self._data = {
            "station": None,
            "blocked": False,
            "silenced": False,
            "violations": [],
            "timestamp": None,
        }

    def update(self, station_id, blocked, violations):
        with self._lock:
            was_blocked = self._data["blocked"]
            silenced = self._data["silenced"]
            # Auto-reset silenced quando violacao cessa
            if was_blocked and not blocked:
                silenced = False
            self._data = {
                "station": station_id,
                "blocked": blocked,
                "silenced": silenced,
                "violations": violations,
                "timestamp": datetime.now().isoformat(),
            }

    def set_silenced(self, value: bool) -> None:
        with self._lock:
            self._data["silenced"] = value

    def get(self):
        with self._lock:
            return self._data.copy()
