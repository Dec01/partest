from partest.utils.ascii import BColors


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
