from partest.parser import OpenAPIParser
from parsettings.settings import swagger_file

class SwaggerSettings:
    def __init__(self):
        self.local_files = swagger_file
        self.swaggers = []

    def add_swagger(self, source_type, path):
        """Добавляет сваггер в список swaggers."""
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

swagger_settings = SwaggerSettings()
swagger_settings.add_swagger('local', swagger_settings.local_files[0])
#swagger_settings.add_swagger('url', 'https://url.ru/swagger.yaml')

# Пример использования
if __name__ == '__main__':
    paths_info = swagger_settings.collect_paths_info()
    for path in paths_info:
        print(f"{path['description']}: \n{path['path']}\n{path['method']}\n{path['parameters']}")
        for param in path['parameters']:
            schema_content = param.schema if param.schema else "Нет схемы"
            print(
                f"Parameter: {param.name}, Type: {param.type}, Required: {param.required}, Description: {param.description}, Schema: {schema_content}")

