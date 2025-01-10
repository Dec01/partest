import os

import yaml
import requests

class Parameter:
    """Class representing a parameter in an API path.

    Attributes:
        name (str): The name of the parameter.
        type (str): The type of the parameter.
        required (bool): Whether the parameter is required or not.
        description (str): A description of the parameter.
        schema (dict): The schema of the parameter.
    """
    def __init__(self, name, param_type, required=False, description='', schema=None):
        """Initializes the Parameter class.

        Args:
            name (str): The name of the parameter.
            param_type (str): The type of the parameter.
            required (bool): Whether the parameter is required or not.
            description (str): A description of the parameter.
            schema (dict): The schema of the parameter.
        """
        self.name = name
        self.type = param_type
        self.required = required
        self.description = description
        self.schema = schema

    def __repr__(self):
        """Returns a string representation of the Parameter object.

        Returns:
            str: A string representation of the Parameter object.
        """
        return f"Parameter(name={self.name}, type={self.type}, required={self.required}, description={self.description}, schema={self.schema})"


class RequestBody:
    """Class representing the request body of an API path.

    Attributes:
        content (dict): The content of the request body.
    """
    def __init__(self, content):
        """Initializes the RequestBody class.

        Args:
            content (dict): The content of the request body.
        """
        self.content = content

    @staticmethod
    def resolve_schema(schema_ref, swagger_dict):
        """Resolves a schema reference.

        Args:
            schema_ref (str): The schema reference.
            swagger_dict (dict): The Swagger dictionary.

        Returns:
            The resolved schema.
        """
        return OpenAPIParser.resolve_ref(schema_ref, swagger_dict)

    def __repr__(self):
        """Returns a string representation of the RequestBody object.

        Returns:
            str: A string representation of the RequestBody object.
        """
        return f"RequestBody(content={self.content})"


class Response:
    """Class representing a response from an API path.

    Attributes:
        status_code (int): The status code of the response.
        content (dict): The content of the response.
    """
    def __init__(self, status_code, content):
        """Initializes the Response class.

        Args:
            status_code (int): The status code of the response.
            content (dict): The content of the response.
        """
        self.status_code = status_code
        self.content = content

    @staticmethod
    def resolve_schema(schema_ref, swagger_dict):
        """Resolves a schema reference.

        Args:
            schema_ref (str): The schema reference.
            swagger_dict (dict): The Swagger dictionary.

        Returns:
            The resolved schema.
        """
        return OpenAPIParser.resolve_ref(schema_ref, swagger_dict)

    def __repr__(self):
        """Returns a string representation of the Response object.

        Returns:
            str: A string representation of the Response object.
        """
        return f"Response(status_code={self.status_code}, content={self.content})"


class Path:
    """Class representing a path in an API.

    Attributes:
        path (str): The path of the API.
        method (str): The HTTP method of the API.
        description (str): A description of the API.
        parameters (list): A list of parameters for the API.
        request_body (dict): The request body of the API.
        responses (dict): The responses of the API.
        deprecated (bool): Whether the API is deprecated or not.
    """
    def __init__(self, path, method, description, parameters, request_body, responses, deprecated=False):
        """Initializes the Path class.

        Args:
            path (str): The path of the API.
            method (str): The HTTP method of the API.
            description (str): A description of the API.
            parameters (list): A list of parameters for the API.
            request_body (dict): The request body of the API.
            responses (dict): The responses of the API.
            deprecated (bool): Whether the API is deprecated or not.
        """
        self.path = path
        self.method = method
        self.description = description
        self.parameters = parameters
        self.request_body = request_body
        self.responses = responses
        self.deprecated = deprecated

    def __repr__(self):
        """Returns a string representation of the Path object.

        Returns:
            str: A string representation of the Path object.
        """
        return f"Path(path={self.path}, method={self.method}, description={self.description}, parameters={self.parameters}, request_body={self.request_body}, responses={self.responses}, deprecated={self.deprecated})"


class OpenAPIParser:
    """Class for parsing OpenAPI specifications.

    Attributes:
        swagger_dict (dict): The Swagger dictionary.
        base_path (str): The base path for the Swagger dictionary.
    """

    def __init__(self, swagger_dict, base_path=''):
        """Initializes the OpenAPIParser class.

        Args:
            swagger_dict (dict): The Swagger dictionary.
            base_path (str): The base path for the Swagger dictionary.
        """
        self.swagger_dict = swagger_dict
        self.base_path = base_path

    @staticmethod
    def load_external_yaml(file_path):
        """Loads an external YAML file.

        Args:
            file_path (str): The path to the YAML file.

        Returns:
            The loaded YAML file.
        """
        with open(file_path, 'r', encoding="utf8") as file:
            return yaml.safe_load(file)

    def resolve_ref(self, ref):
        """Resolves a reference.

        Args:
            ref (str): The reference to resolve.

        Returns:
            The resolved reference.
        """
        if isinstance(ref, dict):
            print("Обнаружен словарь вместо строки, пропускаем.")
            return None

        print(f"Разрешение ссылки: {ref}")

        if ref.startswith('./') or ref.startswith('../'):
            full_path = os.path.join(self.base_path, ref.split('#')[0])
            external_swagger_dict = self.load_external_yaml(full_path)
            internal_ref = ref.split('#')[1]
            return self.resolve_internal_ref(internal_ref, external_swagger_dict)
        else:
            parts = ref.split('/')
            resolved = self.swagger_dict
            for part in parts[1:]:
                if part:
                    resolved = resolved.get(part)
                    if resolved is None:
                        print(
                            f"Ссылка '{ref}' не может быть разрешена в предоставленном словаре swagger, пропускаем.")
                        return None
                else:
                    print("Обнаружена пустая часть ссылки, пропускаем.")
            return resolved

    def resolve_internal_ref(self, internal_ref, swagger_dict):
        """Resolves an internal reference.

        Args:
            internal_ref (str): The internal reference to resolve.
            swagger_dict (dict): The Swagger dictionary.

        Returns:
            The resolved internal reference.
        """
        if not internal_ref:
            raise ValueError("Внутренняя ссылка не может быть пустой.")

        parts = internal_ref.split('/')
        resolved = swagger_dict
        for part in parts:
            if part:
                resolved = resolved.get(part)
                if resolved is None:
                    raise KeyError(
                        f"Ссылка '{internal_ref}' не может быть разрешена в предоставленном словаре swagger.")
            else:
                print("Обнаружена пустая часть ссылки, пропускаем.")

        return resolved

    @classmethod
    def load_swagger_yaml(cls, source_type, file_path=None):
        """Loads the Swagger YAML file from a local file or a URL.

        Args:
            source_type (str): The source type ('local' or 'url').
            file_path (str): The path to the Swagger file.

        Returns:
            An instance of the OpenAPIParser class.
        """
        if source_type == 'local':
            base_path = os.path.dirname(file_path)
            with open(file_path, 'r', encoding="utf8") as file:
                swagger_dict = yaml.safe_load(file)
            return cls(swagger_dict, base_path)
        elif source_type == 'url':
            response = requests.get(file_path)
            response.raise_for_status()
            swagger_dict = yaml.safe_load(response.text)
            return cls(swagger_dict)
        else:
            raise ValueError("Invalid source type. Use 'local' or 'url'.")

    def extract_paths_info(self):
        """Extracts path information from the Swagger specification.

        Returns:
            A list of extracted path information.
        """
        paths = self.swagger_dict.get('paths', {})
        result = []

        for path, methods in paths.items():
            for method, details in methods.items():
                if isinstance(details, dict):
                    parameters = self.extract_parameters(details)
                    request_body = self.extract_request_body(details)
                    responses = self.extract_responses(details)
                    description = self.safe_get_description(details)
                    deprecated = details.get('deprecated', False)
                    result.append(Path(
                        path=path,
                        method=method.upper(),
                        description=description,
                        parameters=parameters,
                        request_body=request_body,
                        responses=responses,
                        deprecated=deprecated
                    ))
                else:
                    print(
                        f"Внимание: ожидались данные в формате dict, но получили {type(details)} для {path} и метода {method}")

        return result

    def extract_parameters(self, details):
        """Extracts parameters from the method details.

        Args:
            details (dict): The method details.

        Returns:
            A list of extracted parameters.
        """
        parameters = []
        if 'parameters' in details:
            for param in details['parameters']:
                resolved_param = self.resolve_param(param)
                parameters.append(resolved_param)
        return parameters

    def extract_request_body(self, details):
        """Extracts the request body from method details.

        Args:
            details (dict): The method details.

        Returns:
            The extracted request body.
        """
        if 'requestBody' in details:
            content = details['requestBody'].get('content', {})
            if 'application/json' in content:
                if 'schema' in content['application/json'] and '$ref' in content['application/json']['schema']:
                    schema_ref = content['application/json']['schema']['$ref']
                    resolved_schema = RequestBody.resolve_schema(schema_ref, self.swagger_dict)
                    content['application/json']['schema'] = resolved_schema
                return RequestBody(content['application/json'])
        return None

    def extract_responses(self, details):
        """Extracts responses from method details.

        Args:
            details (dict): The method details.

        Returns:
            A dictionary of extracted responses.
        """
        responses = {}
        if 'responses' in details:
            for code, response in details['responses'].items():
                if 'content' in response and 'application/json' in response['content']:
                    content = response['content']['application/json']
                    if 'schema' in content and '$ref' in content['schema']:
                        schema_ref = content['schema']['$ref']
                        resolved_schema = Response.resolve_schema(schema_ref, self.swagger_dict)
                        content['schema'] = resolved_schema
                    responses[code] = Response(code, response)
        return responses

    def resolve_param(self, param):
        """Resolves a parameter.

        Args:
            param (dict): The parameter to resolve.

        Returns:
            The resolved parameter.
        """
        if '$ref' in param:
            ref_value = param['$ref']
            resolved_param = self.resolve_ref(ref_value)
            return Parameter(
                name=resolved_param['name'],
                param_type=resolved_param['in'],
                required=resolved_param.get('required', False),
                description=resolved_param.get('description', ''),
                schema=resolved_param.get('schema')
            )
        else:
            return Parameter(
                name=param['name'],
                param_type=param['in'],
                required=param.get('required', False),
                description=param.get('description', ''),
                schema=param.get('schema')
            )

    def safe_get_description(self, details):
        """Safely retrieves the description from details.

        Args:
            details (dict): The details to retrieve the description from.

        Returns:
            The retrieved description.
        """
        if isinstance(details, dict):
            return details.get('description', '')
        elif isinstance(details, list) and details:
            return details[0].get('description', '') if isinstance(details[0], dict) else ''
        return ''


class SwaggerSettings:
    """Class for managing Swagger settings and loading Swagger files.

    Attributes:
        local_files (list): A list of local Swagger files.
        swaggers (list): A list of Swagger definitions.
        paths_info (list): A list of path information.
    """

    def __init__(self, swagger_files):
        """Initializes the SwaggerSettings class.

        Args:
            swagger_files (dict): A dictionary of Swagger files.
        """
        self.local_files = []
        self.swaggers = []
        self.paths_info = []
        self.add_swagger(swagger_files)

    def add_swagger(self, swagger_dict):
        """Adds swagger definitions from a dictionary to the swaggers list.

        Args:
            swagger_dict (dict): A dictionary of Swagger definitions.
        """
        for name, (source_type, path) in swagger_dict.items():
            self.swaggers.append((source_type, path))

    def load_swagger(self):
        """Loads swagger definitions and returns their data.

        Returns:
            list: A list of extracted data from Swagger definitions.
        """
        all_extracted_data = []
        for source_type, path in self.swaggers:
            parser = OpenAPIParser.load_swagger_yaml(source_type, path)
            extracted_data = parser.extract_paths_info()
            all_extracted_data.extend(extracted_data)
        return all_extracted_data

    def collect_paths_info(self):
        """Collects path information from all swagger definitions.

        Returns:
            list: A list of path information.
        """
        extracted_data = self.load_swagger()
        self.paths_info = []

        for item in extracted_data:
            if not item.deprecated:
                self.paths_info.append({
                    'description': item.description,
                    'path': item.path,
                    'method': item.method,
                    'parameters': item.parameters
                })

        return self.paths_info