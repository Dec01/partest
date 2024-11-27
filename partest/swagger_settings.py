from partest.parser import OpenAPIParser
from confpartest import swagger_files

class SwaggerSettings:
    def __init__(self):
        self.local_files = []  # Пустой список для локальных файлов
        self.swaggers = []
        self.add_swagger(swagger_files)  # Добавляем сваггеры из swagger_file

    def add_swagger(self, swagger_dict):
        """Добавляет сваггеры из словаря в список swaggers."""
        for name, (source_type, path) in swagger_dict.items():
            self.swaggers.append((source_type, path))

    def load_swagger(self):
        """Загружает сваггеры и возвращает их данные."""
        all_extracted_data = []
        for source_type, path in self.swaggers:
            parser = OpenAPIParser.load_swagger_yaml(source_type, path)
            extracted_data = parser.extract_paths_info()
            all_extracted_data.extend(extracted_data)
        return all_extracted_data

    def collect_paths_info(self):
        """Собирает информацию о путях из всех сваггеров."""
        extracted_data = self.load_swagger()
        paths_info = []

        for item in extracted_data:
            paths_info.append({
                'description': item.description,
                'path': item.path,
                'method': item.method,
                'parameters': item.parameters
            })
        return paths_info

