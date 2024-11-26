# Install

Для сборки доступны команды:
```
# docker build --build-arg run_env=stage --build-arg run_domen=https://127.0.0.1 -t prosvdev-domen27 .
```
* run_env=name - требуетя указать имя тестируемого окружения (dev/stage)
* run_domen= - требуется указать имя домена поднятного API интерфейса(адрес стенда) 

## Docker: запуск

```
# docker run {name}
or
# docker run -it {name} bash
```
## Docker: отчет
Результат запуска:
reports/pytest/result.xml
```
# pytest --verbose --junitxml=reports\\pytest\\result.xml src/tests/
```
## Общая структура проекта
```
├── prosv
    ├───logs - логирование
    ├───reports - репорты по прогону
    │   └───pytest
    └───src - расположение всех запускаемых тестов
        ├───models
        └───tests
            └───component
```