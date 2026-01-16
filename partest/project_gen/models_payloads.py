import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class PayloadFile:
    name: str
    content: str

class PayloadsContainer:
    def __init__(self, api_reference_path: str):
        self.api_reference_path = Path(api_reference_path)
        self.api_reference = self._load_api_reference()

    def _load_api_reference(self) -> Dict[str, Any]:
        """Загрузка и парсинг api_reference.json."""
        logger.debug(f"Загрузка файла api_reference.json: {self.api_reference_path}")
        try:
            with open(self.api_reference_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Успешно загружен api_reference.json")
                return data
        except Exception as e:
            logger.error(f"Ошибка при загрузке api_reference.json: {e}")
            raise Exception(f"Failed to load api_reference.json: {e}")

    def _snake_to_camel(self, name: str) -> str:
        """Преобразование snake_case в CamelCase."""
        logger.debug(f"Преобразование имени '{name}' в CamelCase")
        camel_name = ''.join(word.capitalize() for word in name.split('_'))
        logger.debug(f"Результат преобразования: {camel_name}")
        return camel_name

    def _get_service_and_subservice(self, endpoint: str) -> tuple[str, str]:
        """Определение сервиса и подсервиса из endpoint."""
        logger.debug(f"Определение сервиса и подсервиса для endpoint: {endpoint}")
        endpoint_details = self.api_reference.get(endpoint, {})
        source = endpoint_details.get('source', {})
        title = source.get('title', 'common').lower().replace(' ', '_').replace('{', '').replace('}', '')
        endpoint_clean = endpoint.split(' ', 1)[-1].lstrip('/')
        parts = endpoint_clean.split('/')
        service = parts[0].lower().replace('{', '').replace('}', '') if parts else "common"
        sub_service = parts[1].lower().replace('{', '').replace('}', '') if len(parts) > 1 else "prefix"
        logger.debug(f"Название:{title}, Сервис: {service}, Подсервис: {sub_service}")
        return service, title

    def _get_faker_method(self, schema: Dict[str, Any], prop_name: str) -> str:
        """Маппинг типов JSON-схемы на методы faker."""
        logger.debug(f"Определение faker-метода для свойства '{prop_name}': {schema}")
        schema_type = schema.get('type')
        schema_format = schema.get('format')
        schema_enum = schema.get('enum')

        if schema_enum:
            logger.debug(f"Свойство '{prop_name}' имеет enum: {schema_enum}")
            return f"lambda: fake.random_element({schema_enum!r})"
        if schema_type == 'string':
            if schema_format == 'uuid':
                logger.debug(f"Свойство '{prop_name}' - UUID, используется fake.uuid4")
                return "fake.uuid4"
            elif schema_format == 'date-time':
                logger.debug(f"Свойство '{prop_name}' - date-time, используется fake.date_time")
                return "lambda: fake.date_time().strftime('%Y-%m-%dT%H:%M:%S.%fZ')"
            elif prop_name in ['phone', 'phone_number']:
                logger.debug(f"Свойство '{prop_name}' - телефон, используется fake.msisdn")
                return "lambda: f'+7{fake.msisdn()[3:]}'"
            elif prop_name in ['email']:
                logger.debug(f"Свойство '{prop_name}' - email, используется fake.email")
                return "fake.email"
            elif prop_name in ['first_name']:
                logger.debug(f"Свойство '{prop_name}' - имя, используется fake.first_name")
                return "fake.first_name"
            elif prop_name in ['last_name']:
                logger.debug(f"Свойство '{prop_name}' - фамилия, используется fake.last_name")
                return "fake.last_name"
            elif prop_name in ['url']:
                logger.debug(f"Свойство '{prop_name}' - URL, используется fake.url")
                return "fake.url"
            elif prop_name in ['userAgent', 'user_agent']:
                logger.debug(f"Свойство '{prop_name}' - userAgent, используется user_a.random")
                return "lambda: user_a.random"
            elif prop_name in ['userTimezone', 'timezone']:
                logger.debug(f"Свойство '{prop_name}' - timezone, возвращается 'Europe/Moscow'")
                return "lambda: 'Europe/Moscow'"
            elif prop_name in ['address']:
                logger.debug(f"Свойство '{prop_name}' - адрес, используется fake.address")
                return "fake.address"
            elif prop_name in ['comment']:
                logger.debug(f"Свойство '{prop_name}' - комментарий, используется fake.sentence")
                return "fake.sentence"
            elif prop_name in ['lat', 'latitude']:
                logger.debug(f"Свойство '{prop_name}' - широта, используется fake.latitude")
                return "lambda: str(fake.latitude())"
            elif prop_name in ['lon', 'longitude']:
                logger.debug(f"Свойство '{prop_name}' - долгота, используется fake.longitude")
                return "lambda: str(fake.longitude())"
            else:
                logger.debug(f"Свойство '{prop_name}' - строка, используется fake.word")
                return "fake.word"
        elif schema_type == 'integer':
            if prop_name in ['userTimestamp', 'timestamp']:
                logger.debug(f"Свойство '{prop_name}' - timestamp, используется fake.unix_time")
                return "lambda: int(fake.unix_time())"
            logger.debug(f"Свойство '{prop_name}' - integer, используется fake.random_int")
            return "lambda: fake.random_int(min=1, max=100)"
        elif schema_type == 'boolean':
            logger.debug(f"Свойство '{prop_name}' - boolean, используется fake.boolean")
            return "fake.boolean"
        elif schema_type == 'object':
            logger.debug(f"Свойство '{prop_name}' - object, возвращается пустой словарь")
            return "lambda: {}"
        elif schema_type == 'array':
            logger.debug(f"Свойство '{prop_name}' - array, возвращается пустой список")
            return "lambda: []"
        logger.warning(f"Неизвестный тип для свойства '{prop_name}': {schema_type}, возвращается fake.word")
        return "fake.word"

    def _generate_payload_class(self, endpoint: str, method: str, request_body: Dict[str, Any]) -> Optional[PayloadFile]:
        """Генерация файла payload для эндпоинта."""
        logger.debug(f"Генерация payload-класса для endpoint: {endpoint}, метод: {method}")
        if not request_body:
            logger.debug(f"Нет requestBody для {endpoint}, пропускаем")
            return None

        endpoint_clean = endpoint.split(' ', 1)[-1].lstrip('/').replace('/', '_').replace('{', '').replace('}', '')
        class_name = f"{method.capitalize()}{self._snake_to_camel(endpoint_clean)}Payload"
        file_name = f"{method.lower()}_{endpoint_clean}_payload.py"
        service, title = self._get_service_and_subservice(endpoint)
        file_path = Path(title) / service / file_name
        logger.debug(f"Имя файла payload: {file_path}, имя класса: {class_name}")

        schema = request_body.get('schema', {})
        required_fields = schema.get('required', [])
        properties = schema.get('properties', {})

        # Формируем _json_main
        json_main_lines = []
        for prop_name, prop_schema in properties.items():
            faker_method = self._get_faker_method(prop_schema, prop_name)
            json_main_lines.append(f'        "{prop_name}": {faker_method}')

        json_main = "{\n" + ",\n".join(json_main_lines) + "\n    }" if json_main_lines else "{}"

        # Формируем содержимое класса
        content_lines = [
            "import json",
            "from fake_useragent import UserAgent",
            "from faker import Faker",
            "",
            "user_a = UserAgent()",
            'fake = Faker(locale="ru_RU")',
            "",
            f"class RequestBody:",
            f'    _required = {required_fields!r}',
            f"    _json_main = {json_main}",
            "",
            "    def __init__(self):",
            "        self._json_serialized = json.dumps(",
            "            {",
            "                key: value() if callable(value) else value",
            "                for key, value in self._json_main.items()",
            "            },",
            '            ensure_ascii=False',
            "        )",
            "",
            "    @property",
            "    def json_serialized(self):",
            "        return self._json_serialized",
            "",
            "    @classmethod",
            "    def get_json_required(cls):",
            "        required_json = {",
            "            key: value() if callable(value) else value",
            "            for key, value in cls._json_main.items()",
            "            if key in cls._required",
            "        }",
            "        return json.dumps(required_json, ensure_ascii=False)",
            "",
            "    @classmethod",
            "    def get_json_miss_required(cls, req):",
            "        required_json = cls.get_json_required()",
            "        json_data = json.loads(required_json)",
            "        if req in json_data:",
            "            json_data.pop(req)",
            "        return json.dumps(json_data, ensure_ascii=False)",
            "",
            "    @classmethod",
            "    def get_required_fields(cls):",
            "        return cls._required",
            "",
            "    def __str__(self):",
            "        return self._json_serialized"
        ]

        content = "\n".join(content_lines)
        logger.debug(f"Сгенерирован payload-класс для {endpoint}:\n{content}")
        return PayloadFile(name=str(file_path), content=content)

    def get_files(self) -> List[PayloadFile]:
        """Генерация файлов payload для всех эндпоинтов с requestBody."""
        logger.debug("Начало генерации файлов payload")
        files = []
        for endpoint, details in self.api_reference.items():
            method = details['method'].lower()
            request_body = details.get('request_body')
            if request_body:
                payload_file = self._generate_payload_class(endpoint, method, request_body)
                if payload_file:
                    files.append(payload_file)
        logger.debug(f"Сгенерировано файлов payload: {len(files)}")
        return files