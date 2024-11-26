import json


class errordesc:
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
        try:
            return "\n\n---->\nОшибка валидации, объекты сравнения:", error, validateModel, '\n', validateData, "\nПодробнее в принт-логах.\n<----\n\n"
        except:
            return "Нет тела или модели"

    @classmethod
    def _ifelse(cls):
        try:
            return "\n\n---->\nНе выполнены условия для выполнения теста, падение.\n<----\n\n"
        except:
            return "Чёт пошло не так"

    @classmethod
    def element(cls, payloadElement=None, dataElement=None, requestBody=None, responseBody=None ):
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
     return "Ответ не валиден"

class StatusCode:
    ok = 200
    bad_request = 400
    not_allowed = 405
    forbidden = 403
    not_found = 404
    exception_400 = [200, 400]