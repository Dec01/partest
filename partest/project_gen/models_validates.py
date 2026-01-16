import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ValidationFile:
    name: str
    content: str

class ValidationsContainer:
    def __init__(self, api_reference_path: str):
        self.api_reference_path = Path(api_reference_path)
        self.api_reference = self._load_api_reference()

    def _load_api_reference(self) -> Dict[str, Any]:
        """Загрузка и парсинг api_reference.json."""
        logger.debug(f"Загрузка файла api_reference.json: {self.api_reference_path}")
        try:
            with open(self.api_reference_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Успешно загружен api_reference.json: {json.dumps(data, indent=2)}")
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

    def _generate_model_name(self, schema: Dict[str, Any], field_name: str = None, is_success: bool = True) -> str:
        """Генерация имени Pydantic-модели."""
        logger.debug(f"Генерация имени модели для схемы: {schema}, field_name: {field_name}, is_success: {is_success}")
        if is_success and field_name:
            model_name = f"ResponseSuccessBody{self._snake_to_camel(field_name)}"
        elif is_success:
            model_name = "ResponseSuccessBody"
        else:
            model_name = "ResponseError"
        logger.debug(f"Сгенерировано имя модели: {model_name}")
        return model_name

    def _get_pydantic_type(self, schema: Dict[str, Any], field_name: str = None) -> str:
        """Маппинг типа JSON-схемы на тип Pydantic."""
        logger.debug(f"Определение Pydantic-типа для схемы: {schema}, field_name: {field_name}")
        schema_type = schema.get('type')
        if schema_type == 'string':
            logger.debug(f"Тип схемы: string, возвращается str")
            return 'str'
        elif schema_type == 'integer':
            logger.debug(f"Тип схемы: integer, возвращается int")
            return 'int'
        elif schema_type == 'boolean':
            logger.debug(f"Тип схемы: boolean, возвращается bool")
            return 'bool'
        elif schema_type == 'array':
            item_schema = schema.get('items', {})
            logger.debug(f"Тип схемы: array, схема элементов: {item_schema}")
            item_type = self._get_pydantic_type(item_schema, field_name)
            logger.debug(f"Тип элементов массива: {item_type}")
            return f"List[{item_type}]"
        elif schema_type == 'object' or schema.get('properties'):
            model_name = self._generate_model_name(schema, field_name)
            logger.debug(f"Тип схемы: object, возвращается имя модели: {model_name}")
            return model_name
        logger.warning(f"Неизвестный тип схемы: {schema_type}, возвращается Any")
        return 'Any'

    def _generate_pydantic_model(self, schema: Dict[str, Any], model_name: str, field_name: str = None, indent: int = 4, generated_models: set = None) -> str:
        """Генерация кода Pydantic-модели для заданной схемы."""
        if generated_models is None:
            generated_models = set()
        logger.debug(f"Генерация Pydantic-модели '{model_name}' для схемы: {json.dumps(schema, indent=2)}, field_name: {field_name}")
        if model_name in generated_models:
            logger.debug(f"Модель '{model_name}' уже сгенерирована, пропускаем")
            return ""
        generated_models.add(model_name)

        indent_str = " " * indent
        lines = []

        # Обработка пустой схемы или схемы без свойств
        if not schema or (not schema.get('properties') and schema.get('type') not in ['array', 'string']):
            logger.debug(f"Схема пустая или без свойств, генерируется пустая модель: {model_name}")
            lines.append(f"class {model_name}(BaseModelWithConfig):")
            lines.append(f"{indent_str}pass")
            return "\n".join(lines)

        # Обработка строки (например, UUID)
        if schema.get('type') == 'string':
            logger.debug(f"Схема типа string, генерируется RootModel: {model_name}")
            lines.append(f"class {model_name}(RootModel):")
            lines.append(f"{indent_str}root: str = Field(...)")
            return "\n".join(lines)

        # Обработка массива
        if schema.get('type') == 'array':
            logger.debug(f"Схема типа array, обработка элементов")
            item_schema = schema.get('items', {})
            item_model_name = self._generate_model_name(item_schema, field_name or 'items')
            logger.debug(f"Имя модели для элементов массива: {item_model_name}")
            item_model_code = self._generate_pydantic_model(item_schema, item_model_name, field_name, indent, generated_models)
            lines.append(f"class {model_name}(BaseModelWithConfig):")
            lines.append(f"{indent_str}items: List[{item_model_name}] = Field(...)")
            logger.debug(f"Сгенерирован код для массива: {lines}")
            return (item_model_code + "\n\n" + "\n".join(lines)) if item_model_code else "\n".join(lines)

        # Обработка объекта
        logger.debug(f"Схема типа object, обработка свойств: {schema.get('properties', {})}")
        lines.append(f"class {model_name}(BaseModelWithConfig):")
        nested_models = []
        for prop_name, prop_schema in schema.get('properties', {}).items():
            logger.debug(f"Обработка свойства '{prop_name}': {prop_schema}")
            prop_type = self._get_pydantic_type(prop_schema, prop_name)
            required = prop_name in schema.get('required', []) or prop_schema.get('nullable', True) is False
            default = "..." if required else "None"
            lines.append(f"{indent_str}{prop_name}: {prop_type} = Field({default})")
            logger.debug(f"Добавлено поле: {prop_name}: {prop_type} = Field({default})")

            # Генерация вложенных моделей для объектов или массивов с объектами
            if prop_schema.get('type') == 'object' or prop_schema.get('properties'):
                nested_model_name = self._generate_model_name(prop_schema, prop_name)
                logger.debug(f"Генерация вложенной модели для объекта: {nested_model_name}")
                nested_model_code = self._generate_pydantic_model(prop_schema, nested_model_name, prop_name, indent, generated_models)
                if nested_model_code:
                    nested_models.append(nested_model_code)
            elif prop_schema.get('type') == 'array' and (prop_schema.get('items', {}).get('type') == 'object' or prop_schema.get('items', {}).get('properties')):
                nested_model_name = self._generate_model_name(prop_schema.get('items'), prop_name)
                logger.debug(f"Генерация вложенной модели для элементов массива: {nested_model_name}")
                nested_model_code = self._generate_pydantic_model(prop_schema.get('items'), nested_model_name, prop_name, indent, generated_models)
                if nested_model_code:
                    nested_models.append(nested_model_code)

        final_code = "\n\n".join(nested_models + ["\n".join(lines)]) if nested_models else "\n".join(lines)
        logger.debug(f"Сгенерирован код модели '{model_name}':\n{final_code}")
        return final_code

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
        logger.debug(f"Сервис: {service}, Подсервис: {sub_service}")
        return service, title

    def _generate_validation_file(self, endpoint: str, method: str, responses: Dict[str, Any]) -> ValidationFile:
        """Генерация файла валидации для endpoint."""
        logger.debug(f"Генерация файла валидации для endpoint: {endpoint}, метод: {method}")
        endpoint_clean = endpoint.split(' ', 1)[-1].lstrip('/').replace('/', '_').replace('{', '').replace('}', '').replace('-', '_')
        file_name = f"{method.lower()}_{endpoint_clean}_validation.py"
        service, title = self._get_service_and_subservice(endpoint)
        file_path = Path(title) / service / file_name
        logger.debug(f"Имя файла валидации: {file_path}")

        content_lines = [
            "from typing import List, Optional",
            "from partest.utils import PydanticResponseError",
            "from pydantic import Field, ValidationError, BaseModel, ConfigDict, RootModel",
            "",
            "",
            "class BaseModelWithConfig(BaseModel):",
            "    model_config = ConfigDict(extra='forbid')",
            ""
        ]

        # Сбрасываем множество сгенерированных моделей для каждого эндпоинта
        generated_models = set()

        # Генерация модели ошибки
        error_schema = {
            "type": "object",
            "properties": {
                "applicationErrorCode": {"type": "string"},
                "message": {"type": "string"},
                "debug": {"type": "string"}
            },
            "required": ["applicationErrorCode", "message", "debug"]
        }
        logger.debug(f"Генерация модели ошибки: {error_schema}")
        error_model_code = self._generate_pydantic_model(error_schema, "ResponseError", generated_models=generated_models)
        content_lines.append(error_model_code)
        content_lines.append("")

        # Генерация моделей для успешных ответов (2xx)
        has_success_model = False
        for response_code, response in responses.items():
            if not response_code.startswith('2'):  # Пропускаем не-2xx ответы
                logger.debug(f"Пропуск ответа с кодом {response_code} (не 2xx)")
                continue
            schema = response.get('schema', {})
            logger.debug(f"Обработка схемы ответа {response_code}: {json.dumps(schema, indent=2)}")
            # Удаление неожиданных параметров
            if 'parameters' in schema:
                logger.warning(f"Удаление неожиданного поля 'parameters' из схемы для {endpoint} ответа {response_code}")
                schema = schema.copy()
                del schema['parameters']
            model_name = self._generate_model_name(schema, is_success=True)
            logger.debug(f"Имя модели для успешного ответа: {model_name}")
            model_code = self._generate_pydantic_model(schema, model_name, indent=4, generated_models=generated_models)
            if model_code:
                logger.debug(f"Сгенерирован код модели для ответа {response_code}:\n{model_code}")
                content_lines.append(model_code)
                content_lines.append("")
                has_success_model = True
            else:
                logger.warning(f"Код модели для ответа {response_code} не сгенерирован")

        # Если не сгенерировано ни одной модели успеха, добавляем пустую
        if not has_success_model:
            logger.debug("Не сгенерировано моделей успеха, добавляется пустая ResponseSuccessBody")
            content_lines.append("class ResponseSuccessBody(BaseModelWithConfig):")
            content_lines.append("    pass")
            content_lines.append("")

        # Генерация классов валидации
        content_lines.append("class ValidateResponseSuccess:")
        content_lines.append("    @staticmethod")
        content_lines.append("    def response_default(data):")
        content_lines.append("        try:")
        content_lines.append("            return ResponseSuccessBody.model_validate(data)")
        content_lines.append("        except ValidationError as e:")
        content_lines.append("            PydanticResponseError.print_error(e)")
        content_lines.append("")

        content_lines.append("class ValidateResponseError:")
        content_lines.append("    @staticmethod")
        content_lines.append("    def response_default(data):")
        content_lines.append("        try:")
        content_lines.append("            return ResponseError.model_validate(data)")
        content_lines.append("        except ValidationError as e:")
        content_lines.append("            PydanticResponseError.print_error(e)")
        content_lines.append("")

        final_content = "\n".join(content_lines)
        logger.debug(f"Сгенерирован файл валидации: {file_path}\nСодержимое:\n{final_content}")
        return ValidationFile(name=str(file_path), content=final_content)

    def get_files(self) -> List[ValidationFile]:
        """Генерация файлов валидации для всех endpoint'ов."""
        logger.debug("Начало генерации файлов валидации для всех endpoint'ов")
        files = []
        for endpoint, details in self.api_reference.items():
            logger.debug(f"Обработка endpoint: {endpoint}, детали: {details}")
            method = details['method'].lower()
            responses = details['responses']
            validation_file = self._generate_validation_file(endpoint, method, responses)
            files.append(validation_file)
        logger.debug(f"Сгенерировано файлов: {len(files)}")
        return files