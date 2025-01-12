import json
from partest.utils import BColors


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
        try:
            body = f'Response body: \n{json.dumps(responseBody.json(), indent=4, ensure_ascii=False)}\n'
        except:
            body = f'Response (non-JSON): {responseBody.text}\n'
        finally:
            desc = (f"\n\n---->\nОшибка! Пришел некорректный статус код!\n"
                    f"Ожидали код: {codeExpected} <\> Получили код: {codeActual}\n"
                    f"{body}\n<----\n\n")
        return desc

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
        try:
            return "\n\n---->\nОшибка валидации, объекты сравнения:", error, validateModel, '\n', validateData, "\nПодробнее в принт-логах.\n<----\n\n"
        except:
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
        try:
            if requestBody is not None and responseBody is not None:
                _resp_body = f'Response body: \n{json.dumps(responseBody.json(), indent=4, ensure_ascii=False)}\n'
                _req_body = f'Request body: \n{json.dumps(requestBody.json(), indent=4, ensure_ascii=False)}\n'
            else:
                _resp_body = ""
                _req_body = ""
        except:
            if requestBody is not None and responseBody is not None:
                _resp_body = f'Response (non-JSON): {responseBody.text}\n'
                _req_body = f'Request (non-JSON): {requestBody.text}\n'
            else:
                _resp_body = ""
                _req_body = ""
        finally:
            desc = (f"\n\n---->\nОшибка! Получили не то значение элемента что ожидали!\n"
                    f"Ожидали значение: {payloadElement} <\> Получили значение: {dataElement}\n"
                    f"{_resp_body}\n{_req_body}\n<----\n\n")
        return desc

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
        print(BColors.WARNING + "\n__________<ReportValidate>__________" + BColors.ENDC)
        print(BColors.BOLD + "Ошибка валидации, тип:" + BColors.ENDC,
              BColors.FAIL + repr(e.errors()[0]['type']),
              ":", repr(e.errors()[0]['msg']) + BColors.ENDC)
        print(BColors.BOLD + "Проблемный ключ:" + BColors.ENDC, repr(e.errors()[0]['loc']))
        print(BColors.BOLD + "Входящее значение:" + BColors.ENDC, repr(e.errors()[0]['input']))
        print(BColors.BOLD + "Полный текст ошибки:" + BColors.ENDC, repr(e.errors()))
        print(BColors.WARNING + "__________</ReportValidate>__________" + BColors.ENDC)