import re
from functools import wraps
from typing import Callable, Dict, Any
from uuid import UUID

from confpartest import swagger_files
from partest.call_storage import call_count, call_type
from partest.parparser import SwaggerSettings

swagger_settings = SwaggerSettings(swagger_files)
paths_info = swagger_settings.collect_paths_info()

def get_component(ref: str) -> Dict[str, Any]:

    ref_parts = ref.split('/')
    if len(ref_parts) > 3 and ref_parts[1] == 'components' and ref_parts[2] == 'parameters':
        param_name = ref_parts[-1]
        return swagger_settings.get_component(ref)  # Assumes this method retrieves the component
    return {}

def track_api_calls(func: Callable) -> Callable:
    """Decorator for tracking API calls."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        method = args[1]
        endpoint = args[2]
        test_type = kwargs.get('type', 'unknown')

        # Collect path parameters from paths_info
        path_params = {}
        for path in paths_info:
            for param in path['parameters']:
                # Check for path parameter directly in parameters
                if param.get('in') == 'path':
                    param_name = param.get('name')
                    if param_name not in path_params:
                        if param.get('schema') is not None:
                            path_params[param_name] = param['schema'].get('enum', [])
                        else:
                            path_params[param_name] = []

                # Check for parameters that are references to other components
                if '$ref' in param:
                    ref_param = get_component(param['$ref'])
                    if ref_param and ref_param.get('in') == 'path':
                        ref_name = ref_param.get('name')
                        path_params[ref_name] = ref_param.get('schema', {}).get('enum', [])

        # Process the add_url parameters
        for i in range(1, 4):
            add_url = kwargs.get(f'add_url{i}')
            if add_url:
                new_param = re.sub(r'^.', '', add_url)
                matched = False
                remaining_param = None
                for param_name, enum_values in path_params.items():
                    if new_param in enum_values:
                        endpoint += '/{' + f'{param_name}' + '}'
                        matched = True
                        break
                    else:
                        remaining_param = param_name

                if not matched and remaining_param:
                    # If no match is found, add the remaining parameter
                    endpoint += '/{' + f'{remaining_param}' + '}'

        # Check if the current method and endpoint match any of the paths_info
        if method is not None and endpoint is not None:
            matched_any = False  # Flag for tracking whether a match has been found
            for path in paths_info:
                if path['method'] == method and path['path'] == endpoint:
                    key = (method, endpoint, path['description'])

                    if key not in call_count:
                        call_count[key] = 0
                        call_type[key] = []
                    call_count[key] += 1
                    call_type[key].append(test_type)
                    matched_any = True
                    break

            # After checking all the paths, add the not found endpoints with 0 calls
            for path in paths_info:
                key = (path['method'], path['path'], path['description'])
                if key not in call_count:
                    call_count[key] = 0
                    call_type[key] = []

        response = await func(*args, **kwargs)

        return response

    return wrapper


def is_valid_uuid(uuid_to_test, version=4):
    """Checks whether the string is a valid UUID."""
    try:
        uuid_obj = UUID(uuid_to_test, version=version)
    except ValueError:
        return False
    return str(uuid_obj) == uuid_to_test