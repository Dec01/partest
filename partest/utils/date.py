from datetime import datetime, timedelta


class DateGen:
    def __init__(self):
        self._current_date = datetime.now()
        self._formats = {
            "default": "%Y-%m-%dT%H:%M:00+03:00",
            "short": "%Y-%m-%d",
            "long": "%Y-%m-%d %H:%M:%S",
        }

    @classmethod
    def get_start_date(cls, days=0, format="default"):
        start_date = cls()._current_date - timedelta(days=days)
        return start_date.strftime(cls()._formats[format])

    @classmethod
    def get_end_date(cls, days=0, format="default"):
        end_date = cls()._current_date + timedelta(days=days)
        return end_date.strftime(cls()._formats[format])

    def __str__(self):
     return self._current_date.strftime("%Y-%m-%d")