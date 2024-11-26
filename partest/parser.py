import yaml
import requests

class Parameter:
    def __init__(self, name, param_type, required=False, description='', schema=None):
        self.name = name
        self.type = param_type
        self.required = required
        self.description = description
        self.schema = schema

    def __repr__(self):
        return f"Parameter(name={self.name}, type={self.type}, required={self.required}, description={self.description}, schema={self.schema})"


class RequestBody:
    def __init__(self, content):
        self.content = content

    @staticmethod
    def resolve_schema(schema_ref, swagger_dict):
        return OpenAPIParser.resolve_ref(schema_ref, swagger_dict)

    def __repr__(self):
        return f"RequestBody(content={self.content})"


class Response:
    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content

    @staticmethod
    def resolve_schema(schema_ref, swagger_dict):
        return OpenAPIParser.resolve_ref(schema_ref, swagger_dict)

    def __repr__(self):
        return f"Response(status_code={self.status_code}, content={self.content})"


class Path:
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
        if source_type == 'local':
            with open(file_path, 'r') as file:
                swagger_dict = yaml.safe_load(file)
        elif source_type == 'url':
            response = requests.get(file_path)
            response.raise_for_status()
            swagger_dict = yaml.safe_load(response.text)
        else:
            raise ValueError("Некорретный тип ресурса. Нужен 'local' или 'url'.")

        return cls(swagger_dict)

    def extract_paths_info(self):
        paths = self.swagger_dict.get('paths', {})
        result = []

        for path, methods in paths.items():
            for method, details in methods.items():
                parameters = []
                if 'parameters' in details:
                    for param in details['parameters']:
                        resolved_param = self.resolve_param(param)
                        parameters.append(resolved_param)

                request_body = None
                if 'requestBody' in details:
                    content = details['requestBody'].get('content', {})
                    if 'application/json' in content:
                        if 'schema' in content['application/json'] and '$ref' in content['application/json']['schema']:
                            schema_ref = content['application/json']['schema']['$ref']
                            resolved_schema = RequestBody.resolve_schema(schema_ref, self.swagger_dict)
                            content['application/json']['schema'] = resolved_schema
                        request_body = RequestBody(content['application/json'])

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

                result.append(Path(
                    path=path,
                    method=method.upper(),
                    description=details.get('description', ''),
                    parameters=parameters,
                    request_body=request_body,
                    responses=responses
                ))

        return result

    def resolve_param(self, param):
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

