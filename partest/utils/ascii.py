class BColors:
    """
    A class used to represent color codes for console output.

    ...

    Attributes
    ----------
    HEADER : str
        Color code for header.
    OKBLUE : str
        Color code for blue text.
    OKCYAN : str
        Color code for cyan text.
    OKGREEN : str
        Color code for green text.
    WARNING : str
        Color code for warning text.
    FAIL : str
        Color code for fail text.
    ENDC : str
        Color code to reset color.
    BOLD : str
        Color code for bold text.
    UNDERLINE : str
        Color code for underlined text.
    """

    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class MethodTypes:
    """
    A class used to represent HTTP method types.

    ...

    Attributes
    ----------
    type_list : list
        List of HTTP method types.
    """
    type_list = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
