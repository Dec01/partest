import json
from partest.utils import BColors
from partest.redact import _body_text, _scrub, _scrub_text

# How much of a body an error description shows, after masking.
_BODY_LIMIT = 2000


def _described(message, label):
    """``<label> body: …`` for a message with ``.json()``, else ``<label> (non-JSON): …``.

    Masked and shortened; never raises, and never falls back to the raw value.
    """
    try:
        data = message.json()
    except Exception:
        try:
            text = getattr(message, "text", message)
        except Exception:
            return f"{label}: <not shown, it could not be read>\n"
        return f"{label} (non-JSON): {_body_text(text, limit=_BODY_LIMIT)}\n"
    return f"{label} body: \n{_body_text(data, limit=_BODY_LIMIT, indent=4)}\n"


class ErrorDesc:
    """
        A class used to represent error descriptions.

        ...

        Attributes
        ----------
        codeExpected : int
            Expected status code.
        codeActual : int
            Actual status code.
        responseBody : str
            Response body.
        responseHeader : str
            Response header.
        requestHeader : str
            Request header.
        requestBody : str
            Request body.
        payloadElement : str
            Payload element.
        dataElement : str
            Data element.

        Methods
        -------
        status(codeExpected=200, codeActual=None, responseBody=None)
            Returns a string describing a status error.
        validate(validateData=None, validateModel=None, error=None)
            Returns a string describing a validation error.
        _ifelse()
            Returns a string describing an if-else error.
        element(payloadElement=None, dataElement=None, requestBody=None, responseBody=None)
            Returns a string describing an element error.
        __str__()
            Returns a string representation of the error.
        """

    def __init__(self):
        self.codeExpected = None
        self.codeActual = None
        self.responseBody = None
        self.responseHeader = None
        self.requestHeader = None
        self.requestBody = None
        self.payloadElement = None
        self.dataElement = None


    @classmethod
    def status(cls, codeExpected=200, codeActual=None, responseBody=None):
        """
        Returns a string describing a status error.

        Parameters
        ----------
        :param codeExpected: Expected status code.
        :param codeActual: Actual status code.
        :param responseBody: Response body.

        Returns
        -------
        :return: String describing a status error.
        """
        # This goes to the ERROR log of every status mismatch, and the body is whatever the
        # service sent: masked and shortened, and a body that cannot be read is a placeholder.
        body = _described(responseBody, "Response")
        return (f"\n\n---->\nОшибка! Пришел некорректный статус код!\n"
                f"Ожидали код: {codeExpected} <\\> Получили код: {codeActual}\n"
                f"{body}\n<----\n\n")

    @classmethod
    def validate(cls, validateData=None, validateModel=None, error=None):
        """
        Returns a string describing a validation error.

        Parameters
        ----------
        :param validateData: Validation data.
        :param validateModel: Validation model.
        :param error: Error.

        Returns
        -------
        :return: String describing a validation error.
        """
        # One string, line by line: the log shows it as written, and a masked value ends at
        # the end of its own line.
        try:
            return (
                "\n\n---->\nОшибка валидации, объекты сравнения:\n"
                f"{error}\n{validateModel}\n{validateData}"
                "\nПодробнее в принт-логах.\n<----\n\n"
            )
        except Exception:
            return "Нет тела или модели"

    @classmethod
    def _ifelse(cls):
        """
        Returns a string describing an if-else error.

        Returns
        -------
        :return: String describing an if-else error.
        """
        try:
            return "\n\n---->\nНе выполнены условия для выполнения теста, падение.\n<----\n\n"
        except:
            return "Чёт пошло не так"

    @classmethod
    def element(cls, payloadElement=None, dataElement=None, requestBody=None, responseBody=None ):
        """
        Returns a string describing an element error.

        Parameters
        ----------
        :param payloadElement: Payload element.
        :param dataElement: Data element.
        :param requestBody: Request body.
        :param responseBody: Response body.

        Returns
        -------
        :return: String describing an element error.
        """
        if requestBody is not None and responseBody is not None:
            _resp_body = _described(responseBody, "Response")
            _req_body = _described(requestBody, "Request")
        else:
            _resp_body = ""
            _req_body = ""
        expected = _body_text(payloadElement, limit=_BODY_LIMIT)
        actual = _body_text(dataElement, limit=_BODY_LIMIT)
        return (f"\n\n---->\nОшибка! Получили не то значение элемента что ожидали!\n"
                f"Ожидали значение: {expected} <\\> Получили значение: {actual}\n"
                f"{_resp_body}\n{_req_body}\n<----\n\n")

    def __str__(self):
        """
        Returns a string representation of the error.

        Returns
        -------
        :return: String representation of the error.
        """
        return "Ответ не валиден"

class StatusCode:
    """
    A class used to represent status codes.

    ...

    Attributes
    ----------
    ok : int
        Status code for OK.
    bad_request : int
        Status code for bad request.
    not_allowed : int
        Status code for not allowed.
    forbidden : int
        Status code for forbidden.
    not_found : int
        Status code for not found.
    exception_400 : list
        List of status codes for exception 400.
    """
    ok = 200
    bad_request = 400
    not_allowed = 405
    forbidden = 403
    not_found = 404
    exception_400 = [200, 400]


class PydanticResponseError:
    @staticmethod
    def print_error(e):
        """Print a pydantic ``ValidationError`` to stdout — without the values it rejected.

        pytest shows this under "Captured stdout" of a failed test, and a rejected value is
        whatever the service sent, a token included. So the input is described by its
        type only and the error list is printed without ``input`` and ``url``; which field did
        not match, and why — path, type, message — is all still there.
        """
        errors = _errors_without_input(e)
        first = errors[0] if errors else {}
        print(BColors.WARNING + "\n__________<ReportValidate>__________" + BColors.ENDC)
        print(BColors.BOLD + "Ошибка валидации, тип:" + BColors.ENDC,
              BColors.FAIL + repr(first.get('type')),
              ":", _scrub_text(repr(first.get('msg'))) + BColors.ENDC)
        print(BColors.BOLD + "Проблемный ключ:" + BColors.ENDC, repr(first.get('loc')))
        print(BColors.BOLD + "Входящее значение:" + BColors.ENDC, _input_kind(e))
        print(BColors.BOLD + "Полный текст ошибки:" + BColors.ENDC, repr(_masked_errors(errors)))
        print(BColors.WARNING + "__________</ReportValidate>__________" + BColors.ENDC)


def _masked_errors(errors):
    """The error list with its values masked — ``msg`` and ``ctx`` — and ``loc`` left as it is.

    Masking the whole ``repr`` read a path like ``('Token', 'b')`` as the pair
    ``('token', <value>)``; a path holds field names, not values.
    """
    out = []
    for err in errors:
        err = dict(err)
        if "msg" in err:
            err["msg"] = _scrub_text(err["msg"])
        if "ctx" in err:
            err["ctx"] = _scrub(err["ctx"])
        out.append(err)
    return out


def _errors_without_input(e):
    try:
        return e.errors(include_input=False, include_url=False)
    except TypeError:  # pydantic before include_input
        return [{k: v for k, v in err.items() if k not in ("input", "url")} for err in e.errors()]


def _input_kind(e):
    """``<str, значение не показывается>`` — the type of the rejected value, never the value."""
    try:
        value = e.errors()[0].get("input")
    except Exception:
        return "<значение не показывается>"
    return f"<{type(value).__name__}, значение не показывается>"