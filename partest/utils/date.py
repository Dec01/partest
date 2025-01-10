from datetime import datetime, timedelta


class DateGen:
    """
    A class used to generate dates.

    ...

    Attributes
    ----------
    _current_date : datetime
        The current date and time.
    _formats : dict
        A dictionary of date formats.

    Methods
    -------
    get_start_date(days=0, format="default")
        Returns the start date.
    get_end_date(days=0, format="default")
        Returns the end date.
    __str__()
        Returns the current date in string format.
    """
    def __init__(self):
        """
        Constructs all the necessary attributes for the DateGen object.

        Parameters
        ----------
        _current_date : datetime
            The current date and time.
        _formats : dict
            A dictionary of date formats.
        """
        self._current_date = datetime.now()
        self._formats = {
            "default": "%Y-%m-%dT%H:%M:00+03:00",
            "short": "%Y-%m-%d",
            "long": "%Y-%m-%d %H:%M:%S",
        }

    @classmethod
    def get_start_date(cls, days=0, format="default"):
        """
        Returns the start date.

        Parameters
        ----------
        days : int, optional
            The number of days to subtract from the current date (default is 0).
        format : str, optional
            The format of the date (default is "default").

        Returns
        -------
        str
            The start date in the specified format.
        """
        start_date = cls()._current_date - timedelta(days=days)
        return start_date.strftime(cls()._formats[format])

    @classmethod
    def get_end_date(cls, days=0, format="default"):
        """
        Returns the end date.

        Parameters
        ----------
        days : int, optional
            The number of days to add to the current date (default is 0).
        format : str, optional
            The format of the date (default is "default").

        Returns
        -------
        str
            The end date in the specified format.
        """
        end_date = cls()._current_date + timedelta(days=days)
        return end_date.strftime(cls()._formats[format])

    def __str__(self):
        """
        Returns the current date in string format.

        Returns
        -------
        str
            The current date in string format.
        """
        return self._current_date.strftime("%Y-%m-%d")