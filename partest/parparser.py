import yaml
import requests

class Parameter:
    """Class representing a parameter in an API path."""
    def __init__(self, name, param_type, required=False, description='', schema=None):
        self.name = name
        self.type = param_type
        self.required = required
        self.description = description
        self.schema = schema

    def __repr__(self):
        return f"Parameter(name={self.name}, type={self.type}, required={self.required}, description={self.description}, schema={self.schema})"


class RequestBody:
    """Class representing the request body of an API path."""
    def __init__(self, content):
        self.content = content

    @staticmethod
    def resolve_schema(schema_ref, swagger_dict):
        return OpenAPIParser.resolve_ref(schema_ref, swagger_dict)

    def __repr__(self):
        return f"RequestBody(content={self.content})"


class Response:
    """Class representing a response from an API path."""
    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content

    @staticmethod
    def resolve_schema(schema_ref, swagger_dict):
        return OpenAPIParser.resolve_ref(schema_ref, swagger_dict)

    def __repr__(self):
        return f"Response(status_code={self.status_code}, content={self.content})"


class Path:
    """Class representing a path in an API."""
    def __init__(self, path, method, description, parameters, request_body, responses):
        self.path = path
        self.method = method
        self.description = description
        self.parameters = parameters
        self.request_body = request_body
        self.responses = responses

    def __repr__(self):
        return f"Path(path={self.path}, method={self.method}, description={self.description}, parameters={self.parameters}, request_body={self.request_body}, responses={self.responses})"


class OpenAPIParser:
    """Class for parsing OpenAPI specifications."""
    def __init__(self, swagger_dict):
        self.swagger_dict = swagger_dict

    @staticmethod
    def resolve_ref(ref, swagger_dict):
        parts = ref.split('/')
        resolved = swagger_dict
        for part in parts[1:]:
            resolved = resolved[part]
        return resolved

    @classmethod
    def load_swagger_yaml(cls, source_type, file_path=None):
        """Loads the Swagger YAML file from a local file or a URL."""
        if source_type == 'local':
            with open(file_path, 'r') as file:
                swagger_dict = yaml.safe_load(file)
        elif source_type == 'url':
            response = requests.get(file_path)
            response.raise_for_status()
            swagger_dict = yaml.safe_load(response.text)
        else:
            raise ValueError("Invalid source type. Use 'local' or 'url'.")

        return cls(swagger_dict)

    def extract_paths_info(self):
        """Extracts path information from the Swagger specification."""
        paths = self.swagger_dict.get('paths', {})
        result = []

        for path, methods in paths.items():
            for method, details in methods.items():
                parameters = self.extract_parameters(details)
                request_body = self.extract_request_body(details)
                responses = self.extract_responses(details)
                description = self.safe_get_description(details)
                result.append(Path(
                    path=path,
                    method=method.upper(),
                    description=description,
                    parameters=parameters,
                    request_body=request_body,
                    responses=responses
                ))

        return result

    def extract_parameters(self, details):
        """Extracts parameters from the method details."""
        parameters = []
        if 'parameters' in details:
            for param in details['parameters']:
                resolved_param = self.resolve_param(param)
                parameters.append(resolved_param)
        return parameters

    def extract_request_body(self, details):
        """Extracts the request body from method details."""
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
        """Extracts responses from method details."""
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
        """Resolves a parameter definition."""
        if '$ref' in param:
            resolved_param = self.resolve_ref(param['$ref'], self.swagger_dict)
            schema_content = None
            if 'schema' in resolved_param and '$ref' in resolved_param['schema']:
                schema_ref = resolved_param['schema']['$ref']
                schema_content = self.resolve_ref(schema_ref, self.swagger_dict)
            return Parameter(
                name=resolved_param['name'],
                param_type=resolved_param['in'],
                required=resolved_param.get('required', False),
                description=resolved_param.get('description', ''),
                schema=schema_content
            )
        else:
            schema_content = None
            if 'schema' in param and '$ref' in param['schema']:
                schema_ref = param['schema']['$ref']
                schema_content = self.resolve_ref(schema_ref, self.swagger_dict)

            return Parameter(
                name=param['name'],
                param_type=param['in'],
                required=param.get('required', False),
                description=param.get('description', ''),
                schema=schema_content
            )

    def safe_get_description(self, details):
        """Safely retrieves the description from details."""
        if isinstance(details, dict):
            return details.get('description', '')
        elif isinstance(details, list) and details:
            return details[0].get('description', '') if isinstance(details[0], dict) else ''
        return ''


class SwaggerSettings:
    """Class for managing Swagger settings and loading Swagger files."""
    def __init__(self, swagger_files):
        self.local_files = []
        self.swaggers = []
        self.add_swagger(swagger_files)

    def add_swagger(self, swagger_dict):
        """Adds swaggger definitions from a dictionary to the swaggers list."""
        for name, (source_type, path) in swagger_dict.items():
            self.swaggers.append((source_type, path))

    def load_swagger(self):
        """Loads swaggger definitions and returns their data."""
        all_extracted_data = []
        for source_type, path in self.swaggers:
            parser = OpenAPIParser.load_swagger_yaml(source_type, path)
            extracted_data = parser.extract_paths_info()
            all_extracted_data.extend(extracted_data)
        return all_extracted_data

    def collect_paths_info(self):
        """Collects path information from all swagger definitions."""
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