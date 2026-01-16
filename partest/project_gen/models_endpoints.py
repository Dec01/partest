import json
from typing import Dict, List
from pathlib import Path


class EndpointFile:
    """Class representing a single endpoint file with name and content."""

    def __init__(self, name: str, content: str):
        """
        Initialize an EndpointFile object.

        Args:
            name (str): The name of the file (e.g., 'paths.py').
            content (str): The content of the file.
        """
        self.name = name
        self.content = content

    def __repr__(self):
        """Return a string representation of the EndpointFile object."""
        return f"EndpointFile(name='{self.name}', content_length={len(self.content)})"


class EndpointsContainer:
    """Class to manage endpoint files (paths.py and config.py) generated from api_reference.json."""

    def __init__(self, api_reference_path: str):
        """
        Initialize the container with endpoint files based on api_reference.json.

        Args:
            api_reference_path (str): Path to the api_reference.json file.
        """
        self.api_reference_path = api_reference_path
        self.api_reference = self._load_api_reference()
        self.files = self._generate_endpoint_files()

    def _load_api_reference(self) -> Dict:
        """Load and parse the api_reference.json file."""
        try:
            with open(self.api_reference_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки api_reference.json: {e}")
            return {}

    def _generate_paths_content(self) -> str:
        """Generate content for paths.py based on api_reference.json."""
        # Extract unique paths and group by service prefix
        services = {}
        unique_paths = set()

        # Collect unique paths
        for endpoint_key, data in self.api_reference.items():
            path = data.get("path", "")
            if path and path not in unique_paths:
                unique_paths.add(path)

        # Group paths by service
        for path in unique_paths:
            # Skip empty or malformed paths
            if not path.startswith("/"):
                continue

            # Extract service name and endpoint name
            parts = path.strip("/").split("/")
            if len(parts) < 1:
                continue

            # Handle /users/profile/* paths under UsersProfile
            if parts[0] == "users" and len(parts) > 1 and parts[1] == "profile":
                service_name = "UsersProfile"
                endpoint_parts = parts[2:]  # Start after /users/profile
            else:
                service_name = parts[0].capitalize()
                endpoint_parts = parts[1:]

            endpoint_name = "_".join(endpoint_parts) if endpoint_parts else "root"
            endpoint_name = endpoint_name.replace("{", "").replace("}", "").replace("-", "_").replace(".", "_") or "root"

            # Remove dynamic parameters from path (e.g., /user/{id} -> /user/)
            clean_path = "/".join(p for p in parts if not (p.startswith("{") and p.endswith("}")))
            # Add trailing slash for paths with dynamic parameters
            has_dynamic_param = len(parts) > len(clean_path.split("/"))
            clean_path = f"/{clean_path}/" if has_dynamic_param else f"/{clean_path}"

            if service_name not in services:
                services[service_name] = {}
            services[service_name][endpoint_name] = clean_path

        # Generate paths.py content
        content = ["from dataclasses import dataclass", "from typing import Optional", ""]
        content.append('API_PREFIX = "/api/v1/pages"')
        content.append("")
        content.append("@dataclass")
        content.append("class Paths:")
        for service_name, endpoints in services.items():
            content.append(f"    class {service_name}:")
            service_prefix = f"{{API_PREFIX}}/{service_name.lower() if service_name != 'UsersProfile' else 'users/profile'}"
            content.append(f'        prefix = f"{service_prefix}"')
            for endpoint_name, path in endpoints.items():
                if endpoint_name == "root" and path.strip("/") == (
                        service_name.lower() if service_name != 'UsersProfile' else "users/profile"):
                    continue  # Skip root endpoint if it matches prefix
                relative_path = path[
                               len(f"/{service_name.lower() if service_name != 'UsersProfile' else 'users/profile'}"):].strip(
                    "/") or ""
                # Ensure trailing slash for dynamic parameters
                if endpoint_name.endswith("_id") or endpoint_name.endswith("_filter"):
                    content.append(f'        {endpoint_name} = f"{{prefix}}/{relative_path}/"')
                else:
                    content.append(f'        {endpoint_name} = f"{{prefix}}/{relative_path}"')
            content.append("")
        content.append("    def get_path(self, service: str, endpoint: str) -> Optional[str]:")
        content.append("        svc = getattr(self, service, None)")
        content.append("        if svc:")
        content.append("            return getattr(svc, endpoint, None)")
        content.append("        return None")
        content.append("")

        return "\n".join(content)

    def _generate_config_content(self) -> str:
        """Generate content for config.py based on api_reference.json."""
        # Extract endpoint configurations
        services = {}
        header_generators = {
            "User-Agent": "lambda: self._ua.random",
            "Accept": 'lambda: "application/json"',
            "Content-Type": 'lambda: "application/json"',
            "X-Request-ID": "lambda: self._faker.uuid4()",
            "Authorization": 'lambda token: f"Bearer {token}"',
            "X-Client": "lambda: self._faker.uuid4()",
            "X-API-Version": 'lambda: f"{random.randint(1, 5)}.{random.randint(0, 9)}"',
        }
        param_generators = {
            "offset": "lambda: random.randint(0, 1000)",
            "limit": "lambda: random.randint(1, 1000)",
        }

        for endpoint_key, data in self.api_reference.items():
            path = data.get("path", "")
            method = data.get("method", "").lower()
            parameters = data.get("parameters", [])

            # Skip empty or malformed paths
            if not path.startswith("/"):
                continue

            # Extract service and endpoint name
            parts = path.strip("/").split("/")
            if len(parts) < 1:
                continue

            # Handle /users/profile/* paths under users_profile
            if parts[0] == "users" and len(parts) > 1 and parts[1] == "profile":
                service_name = "users_profile"
                endpoint_parts = parts[2:]  # Start after /users/profile
            else:
                service_name = parts[0]
                endpoint_parts = parts[1:]

            endpoint_name = "_".join(endpoint_parts) if endpoint_parts else "root"
            endpoint_name = endpoint_name.replace("{", "").replace("}", "").replace("-", "_").replace(".", "_") or "root"

            if service_name not in services:
                services[service_name] = {}

            # Extract headers and query params only
            headers = [p["name"] for p in parameters if p.get("type") == "header"]
            params = [p["name"] for p in parameters if p.get("type") == "query"]
            header_config = {}
            param_config = {}

            # Process headers
            for p in parameters:
                if p.get("type") == "header":
                    param_name = p["name"]
                    schema = p.get("schema", {})
                    enum = schema.get("enum")
                    example = schema.get("example")
                    param_type = schema.get("type")
                    if enum:
                        header_config[param_name] = {"values": enum}
                        if param_name not in header_generators:
                            header_generators[param_name] = f"lambda: random.choice({enum})"
                    elif example is not None:
                        header_config[param_name] = {"fixed_value": example}
                        if param_name not in header_generators:
                            header_generators[param_name] = f"lambda: {json.dumps(example)}"
                    elif param_type == "string":
                        header_config[param_name] = {"fixed_value": "default"}
                        if param_name not in header_generators:
                            header_generators[param_name] = 'lambda: "default"'
                    else:
                        header_config[param_name] = {"fixed_value": "default"}
                        if param_name not in header_generators:
                            header_generators[param_name] = 'lambda: "default"'

            # Process query params
            for p in parameters:
                if p.get("type") == "query":
                    param_name = p["name"]
                    schema = p.get("schema", {})
                    enum = schema.get("enum")
                    example = schema.get("example")
                    param_type = schema.get("type")
                    param_format = schema.get("format")
                    if enum:
                        param_config[param_name] = {"values": enum}
                        if param_name not in param_generators:
                            param_generators[param_name] = f"lambda: random.choice({enum})"
                    elif example is not None:
                        param_config[param_name] = {"fixed_value": example}
                        if param_name not in param_generators:
                            param_generators[param_name] = f"lambda: {json.dumps(example)}"
                    elif param_format == "uuid":
                        param_config[param_name] = {"generator": "self._faker.uuid4"}
                        if param_name not in param_generators:
                            param_generators[param_name] = "lambda: self._faker.uuid4()"
                    elif param_type == "string":
                        param_config[param_name] = {"fixed_value": "default"}
                        if param_name not in param_generators:
                            param_generators[param_name] = 'lambda: "default"'
                    elif param_type == "integer":
                        param_config[param_name] = {"generator": "random.randint(1, 100)"}
                        if param_name not in param_generators:
                            param_generators[param_name] = "lambda: random.randint(1, 100)"
                    else:
                        param_config[param_name] = {"fixed_value": "default"}
                        if param_name not in param_generators:
                            param_generators[param_name] = 'lambda: "default"'

            # Store or update endpoint config
            if endpoint_name in services[service_name]:
                services[service_name][endpoint_name]["headers"].extend(headers)
                services[service_name][endpoint_name]["params"].extend(params)
                services[service_name][endpoint_name]["header_config"].update(header_config)
                services[service_name][endpoint_name]["param_config"].update(param_config)
            else:
                services[service_name][endpoint_name] = {
                    "headers": headers,
                    "params": params,
                    "header_config": header_config,
                    "param_config": param_config
                }

        # Remove duplicates in headers and params
        for service_name, endpoints in services.items():
            for endpoint_name, config in endpoints.items():
                config["headers"] = list(set(config["headers"]))
                config["params"] = list(set(config["params"]))

        # Generate config.py content
        content = [
            "from dataclasses import dataclass",
            "from typing import Dict, List, Callable",
            "from faker import Faker",
            "from fake_useragent import UserAgent",
            "import random",
            "",
            "@dataclass",
            "class Endpoint:",
            "    headers: List[str] = None",
            "    params: List[str] = None",
            "    header_config: Dict[str, dict] = None",
            "    param_config: Dict[str, dict] = None",
            "",
            "    def __post_init__(self):",
            "        self.headers = self.headers or []",
            "        self.header_config = self.header_config or {}",
            "        self.params = self.params or []",
            "        self.param_config = self.param_config or {}",
            "",
            "@dataclass",
            "class Service:",
            "    endpoints: Dict[str, Endpoint] = None",
            "",
            "    def __post_init__(self):",
            "        self.endpoints = self.endpoints or {}",
            "",
            "@dataclass",
            "class EndpointConfig:",
            "    services: Dict[str, Service] = None",
            "    header_generators: Dict[str, Callable] = None",
            "    param_generators: Dict[str, Callable] = None",
            "",
            "    def __post_init__(self):",
            "        self.services = self.services or {}",
            '        self._faker = Faker(locale="ru_RU")',
            "        self._ua = UserAgent()",
            "",
            "        self.header_generators = self.header_generators or {",
        ]
        for key, value in header_generators.items():
            content.append(f'            "{key}": {value},')
        content.append("        }")
        content.append("")
        content.append("        self.param_generators = self.param_generators or {")
        for key, value in param_generators.items():
            content.append(f'            "{key}": {value},')
        content.append("        }")
        content.append("")
        content.append("    def get_endpoint_config(self, service: str, endpoint: str) -> Endpoint:")
        content.append("        svc = self.services.get(service, None)")
        content.append('        if svc is None or endpoint not in svc.endpoints:')
        content.append('            raise ValueError(f"Конфигурация для {service}/{endpoint} не найдена")')
        content.append("        return svc.endpoints[endpoint]")
        content.append("")
        content.append("config = EndpointConfig(")
        content.append("    services={")
        for service_name, endpoints in services.items():
            content.append(f'        "{service_name}": Service(')
            content.append("            endpoints={")
            for endpoint_name, config in endpoints.items():
                content.append(f'                "{endpoint_name}": Endpoint(')
                content.append(f'                    headers={config["headers"]},')
                content.append(f'                    header_config={config["header_config"]},')
                content.append(f'                    params={config["params"]},')
                content.append(f'                    param_config={config["param_config"]}')
                content.append("                ),")
            content.append("            }")
            content.append("        ),")
        content.append("    }")
        content.append(")")

        return "\n".join(content)

    def _generate_endpoint_files(self) -> List[EndpointFile]:
        """Generate paths.py and config.py based on api_reference.json."""
        paths_content = self._generate_paths_content()
        config_content = self._generate_config_content()
        return [
            EndpointFile(name="paths.py", content=paths_content),
            EndpointFile(name="configs.py", content=config_content)
        ]

    def get_files(self) -> List[EndpointFile]:
        """Return the list of endpoint files."""
        return self.files

    def get_file_by_name(self, name: str) -> EndpointFile:
        """Retrieve an endpoint file by its name."""
        for file in self.files:
            if file.name == name:
                return file
        return None