import os
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import uuid

class TestFile:
    """Класс, представляющий тестовый файл с именем и содержимым."""

    def __init__(self, name: str, content: str):
        """
        Инициализация объекта TestFile.

        Args:
            name (str): Имя тестового файла (например, 'addresses/test_addresses_default.py').
            content (str): Содержимое тестового файла.
        """
        self.name = name
        self.content = content

    def __repr__(self):
        """Возвращает строковое представление объекта TestFile."""
        return f"TestFile(name='{self.name}', content_length={len(self.content)})"

class TestsContainer:
    """Класс для управления генерацией тестовых файлов на основе api_reference.json."""

    def __init__(self, api_reference_path: str):
        """
        Инициализация контейнера с тестовыми файлами на основе JSON-файла API.

        Args:
            api_reference_path (str): Путь к файлу api_reference.json.
        """
        self.api_reference_path = Path(api_reference_path)
        self.tests_dir = self.api_reference_path.parent / "src" / "tests"
        self.api_reference = self._load_api_reference()
        self.endpoint_groups = self._get_endpoint_groups()
        self.id_mappings = self._predict_id_usage()
        self.files = self._generate_test_files()

    def _load_api_reference(self) -> Dict[str, Any]:
        """Загрузка и парсинг api_reference.json."""
        with open(self.api_reference_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _clean_name(self, name: str) -> str:
        """Удаляет фигурные скобки и другие недопустимые символы из имени."""
        return name.replace("{", "").replace("}", "").replace("-", "_").replace(".", "_").replace(" ", "_")

    def _get_service_and_title(self, endpoint: str) -> tuple[str, str]:
        """Определение сервиса и title из endpoint."""
        endpoint_details = self.api_reference.get(endpoint, {})
        source = endpoint_details.get('source', {})
        title = source.get('title', 'common').lower().replace(' ', '_').replace('{', '').replace('}', '')
        endpoint_clean = endpoint.split(' ', 1)[-1].lstrip('/')
        parts = endpoint_clean.split('/')
        service = parts[0].lower().replace('{', '').replace('}', '') if parts else 'common'
        if service == "users_profile":
            service = "profile"
        return service, title

    def _get_endpoint_groups(self) -> Dict[str, List[Dict]]:
        """
        Группировка эндпоинтов из api_reference.json по сервису.

        Returns:
            Dict: Словарь, где ключ — сервис, значение — список деталей эндпоинтов.
        """
        groups = {}
        for endpoint_path, endpoint_data in self.api_reference.items():
            path_parts = endpoint_path.split('/')
            service, title = self._get_service_and_title(endpoint_path)
            service = self._clean_name(service)
            if service not in groups:
                groups[service] = []

            path_parameters = [param['name'] for param in endpoint_data.get('parameters', []) if param['type'] == 'path']

            groups[service].append({
                'path': endpoint_path,
                'method': endpoint_data.get('method', '').upper(),
                'description': endpoint_data.get('description', ''),
                'parameters': endpoint_data.get('parameters', []),
                'request_body': endpoint_data.get('request_body', None),
                'responses': endpoint_data.get('responses', {}),
                'endpoint_name': self._clean_name(path_parts[-1]),
                'path_parameters': path_parameters,
                'title': title
            })

        return groups

    def _get_path_parameters(self, service: str) -> List[str]:
        """
        Получение уникальных параметров пути из зависимых эндпоинтов сервиса.

        Args:
            service (str): Имя сервиса.

        Returns:
            List[str]: Список уникальных параметров пути.
        """
        endpoints = self._get_endpoint_groups()[service]
        unique_params = set()
        for endpoint in endpoints:
            if endpoint['method'] != 'POST' and endpoint.get('path_parameters'):
                unique_params.update(endpoint['path_parameters'])
        return list(unique_params)

    def _find_resource_id_field(self, service: str, responses: Dict) -> Optional[str]:
        """
        Определяет поле в схеме ответа, которое может быть использовано как resource_id.

        Args:
            service (str): Имя сервиса.
            responses (Dict): Словарь ответов эндпоинта из api_reference.json.

        Returns:
            Optional[str]: Имя поля, если найдено, иначе None.
        """
        path_params = self._get_path_parameters(service)
        success_response = next((r for r in responses.values() if str(r.get('status_code')).startswith('2')), None)
        if not success_response or not success_response.get('schema'):
            return None

        schema = success_response['schema']
        content_type = success_response.get('content_type')

        if content_type == 'text/plain' and schema.get('type') == 'string' and schema.get('format') == 'uuid':
            base_path = service.lower()
            return f"{base_path}Id"
        elif schema.get('type') == 'string':
            return 'response'
        elif schema.get('type') == 'object' and schema.get('properties'):
            properties = schema['properties']
            for param in path_params:
                if param in properties:
                    return param
            for param in path_params:
                snake_case = param.replace('Id', '_id').lower()
                if snake_case in properties:
                    return snake_case
            for field in properties:
                if 'id' in field.lower() and properties[field].get('format') == 'uuid':
                    return field
        return None

    def _predict_id_usage(self) -> Dict[str, Dict]:
        """
        Предсказывает, какие поля ID нужно сохранить и где их использовать.

        Returns:
            Dict: Словарь с маппингом ID для каждого сервиса.
        """
        id_mappings = {}
        api_reference = self.endpoint_groups

        for service, endpoints in api_reference.items():
            for endpoint in endpoints:
                if endpoint['method'] == 'POST':
                    success_codes = ['200', '201']
                    for code in success_codes:
                        if code in endpoint['responses']:
                            resp = endpoint['responses'][code]
                            id_field = self._find_resource_id_field(service, endpoint['responses'])
                            if id_field:
                                method = endpoint['method'].lower()
                                endpoint_name = endpoint['endpoint_name']
                                # Для рутовых эндпоинтов убираем дублирование в имени теста
                                test_name_suffix = "default" if endpoint_name == service else f"{endpoint_name}_default"
                                source_test_name = f"test_{method}_{service}_{test_name_suffix}"
                                id_mappings[service] = {
                                    'source': endpoint['path'],
                                    'source_test_name': source_test_name,
                                    'id_field': id_field,
                                    'used_in': []
                                }

        for service, endpoints in api_reference.items():
            if service in id_mappings:
                for endpoint in endpoints:
                    if endpoint['method'] in ['GET', 'PUT', 'DELETE', 'PATCH']:
                        for param in endpoint['parameters']:
                            if param['type'] == 'path':
                                param_name = param['name']
                                id_field = id_mappings[service]['id_field']
                                if param_name == id_field or 'id' in param_name.lower():
                                    id_mappings[service]['used_in'].append(endpoint['path'])

        return id_mappings

    def _generate_test_content(self, service: str, endpoints: List[Dict]) -> str:
        """
        Генерация содержимого тестового файла для определённого сервиса.

        Args:
            service (str): Имя сервиса (например, 'address').
            endpoints (List[Dict]): Список деталей эндпоинтов.

        Returns:
            str: Содержимое тестового файла.
        """
        title = endpoints[0]['title'] if endpoints else 'common'
        content = [
            "import allure",
            "import pytest",
            "",
            "",
            f"@allure.story('{service.capitalize()}')",
            '@allure.label("suite", "API")',
            f'@allure.label("component", "{service.capitalize()}")',
            f'@allure.label("owner", "{title.capitalize()}")',
            "@pytest.mark.asyncio",
            f"class Test{service.capitalize()}Default:"
        ]

        if service in self.id_mappings:
            content.append(f"    resource_id: str = None")
        content.append("")

        method_order = {'POST': 0, 'PUT': 1, 'GET': 2, 'PATCH': 3, 'DELETE': 4}

        for endpoint in sorted(endpoints, key=lambda x: (method_order.get(x['method'], 5), x['path'])):
            method = endpoint['method']
            endpoint_name = endpoint['endpoint_name']
            path_key = service if endpoint_name == service else f"{service}_{endpoint_name}"
            responses = endpoint['responses']
            success_response = next((r for r in responses.values() if str(r.get('status_code')).startswith('2')), None)

            if not success_response:
                continue

            expected_status = success_response.get('status_code')
            # Для рутовых эндпоинтов убираем дублирование в имени теста
            test_name_suffix = "default" if endpoint_name == service else f"{endpoint_name}_default"
            if endpoint['path_parameters'] and endpoint_name != service:
                test_name_suffix = f"{endpoint_name}_id_default"
            test_name = f"test_{method.lower()}_{service}_{test_name_suffix}"
            # Для моделей валидации и payload тоже убираем дублирование
            model_name = service if endpoint_name == service else f"{service}_{endpoint_name}"
            validate_model = f"models.{title.lower()}.validate.{method.lower()}_{model_name}_validation_success"
            headers = f"models.{title.lower()}.headers.auth"
            data_type = None
            dependency = None

            if service in self.id_mappings and endpoint['path'] in self.id_mappings[service]['used_in']:
                dependency = self.id_mappings[service]['source_test_name']
                path_param = endpoint['path_parameters'][0] if endpoint['path_parameters'] else 'id'

            if endpoint['request_body'] and method in ['POST', 'PUT']:
                data_type = f"models.{title.lower()}.payload.{method.lower()}_{model_name}_payload_default"

            dependency_line = f", depends=['{dependency}'], force=True" if dependency else ""
            content.append(f"    @pytest.mark.dependency(name='{test_name}'{dependency_line})")
            content.append(f"    async def {test_name}(self, domain, api_client, models):")
            if dependency:
                content.append(f"        add_url = f'{{self.__class__.resource_id}}'")
            content.append("        response = await api_client.make_request(")
            content.append(f"            '{method}',")
            content.append(f"            models.{title.lower()}.paths.{path_key},")
            content.append(f"            headers={headers},")
            if data_type:
                content.append(f"            data_type={data_type},")
            if dependency:
                content.append(f"            add_url1=add_url,")
            content.append(f"            expected_status_code={expected_status},")
            if success_response.get('schema', {}).get('type') != 'null':
                content.append(f"            validate_model={validate_model}")
            content.append("        )")

            if expected_status == 201 and service in self.id_mappings:
                resource_field = self.id_mappings[service]['id_field']
                if resource_field == 'response':
                    content.append("        assert response is not None")
                    content.append("        self.__class__.resource_id = response")
                else:
                    content.append(f"        # Автоматически выбрано поле '{resource_field}' для resource_id")
                    content.append("        assert response is not None")
                    content.append(f"        self.__class__.resource_id = response['{resource_field}']")
            elif expected_status == 204:
                content.append("        assert response == ''")
            else:
                content.append("        assert response is not None")
            content.append("")

        return "\n".join(content)

    def _generate_test_files(self) -> List[TestFile]:
        """
        Генерация тестовых файлов на основе групп эндпоинтов с вложенной структурой директорий.

        Returns:
            List[TestFile]: Список объектов TestFile.
        """
        test_files = []
        for service, endpoints in self.endpoint_groups.items():
            title = endpoints[0]['title'] if endpoints else 'common'
            file_name = f"{title}/{service}/test_{service}_default.py"
            content = self._generate_test_content(service, endpoints)
            test_files.append(TestFile(name=file_name, content=content))

        return test_files

    def get_files(self) -> List[TestFile]:
        """Возвращает список тестовых файлов."""
        return self.files

    def get_file_by_name(self, name: str) -> Optional[TestFile]:
        """Получение тестового файла по имени."""
        for file in self.files:
            if file.name == name:
                return file
        return None