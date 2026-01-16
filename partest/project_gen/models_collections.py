import os
from pathlib import Path
from typing import Dict, List
import ast
import importlib.util
import sys

class CollectionFile:
    """Class representing a collection file with name and content."""

    def __init__(self, name: str, content: str):
        """
        Initialize a CollectionFile object.

        Args:
            name (str): The name of the file (e.g., 'users_collection.py').
            content (str): The content of the file.
        """
        self.name = name
        self.content = content

    def __repr__(self):
        """Return a string representation of the CollectionFile object."""
        return f"CollectionFile(name='{self.name}', content_length={len(self.content)})"

class CollectionsContainer:
    """Class to manage the generation of collection files based on existing files."""

    def __init__(self, project_dir: str):
        """
        Initialize the container with collection files based on existing validation, payload, and endpoint files.

        Args:
            project_dir (str): Path to the project directory containing src/models.
        """
        self.project_dir = Path(project_dir)
        self.validations_dir = self.project_dir / "src" / "models" / "validations"
        self.payloads_dir = self.project_dir / "src" / "models" / "payloads"
        self.endpoints_dir = self.project_dir / "src" / "models" / "endpoints"
        self.paths_file = self.endpoints_dir / "paths.py"
        self.config_file = self.endpoints_dir / "config.py"
        self.files = self._generate_collection_file()

    def _clean_name(self, name: str) -> str:
        """Remove curly braces and other invalid characters from file or folder names."""
        return name.replace("{", "").replace("}", "").replace("-", "_").replace(".", "_")

    def _get_service_structure(self, directory: Path) -> Dict[str, Dict[str, List[str]]]:
        """
        Scan a directory to get its structure (services, subservices, and files).

        Args:
            directory (Path): Directory to scan (e.g., validations, payloads, endpoints).

        Returns:
            Dict: Nested dictionary of services, subservices, and files.
        """
        structure = {}
        if not directory.exists():
            return structure

        for service_dir in sorted(directory.iterdir()):
            if service_dir.is_dir():
                service_name = self._clean_name(service_dir.name)
                structure[service_name] = {}
                for subservice_dir in sorted(service_dir.iterdir()):
                    if subservice_dir.is_dir():
                        subservice_name = self._clean_name(subservice_dir.name)
                        structure[service_name][subservice_name] = []
                        for file in sorted(subservice_dir.iterdir()):
                            if file.is_file() and file.suffix == ".py" and file.name != "__init__.py":
                                structure[service_name][subservice_name].append(self._clean_name(file.stem))
                    elif subservice_dir.is_file() and subservice_dir.suffix == ".py" and subservice_dir.name != "__init__.py":
                        if "root" not in structure[service_name]:
                            structure[service_name]["root"] = []
                        structure[service_name]["root"].append(self._clean_name(subservice_dir.stem))
        return structure

    def _format_import_line(self, base_path: str, files: List[str]) -> str:
        """
        Format an import line for multiple files from the same directory.

        Args:
            base_path (str): Base import path (e.g., 'src.models.validations.users.address').
            files (List[str]): List of file names to import.

        Returns:
            str: Formatted import statement, with line breaks and commas at the end of lines.
        """
        if not files:
            return ""
        max_line_length = 88  # PEP 8 max line length
        import_prefix = f"from {base_path} import "
        files = sorted(files)
        lines = []
        current_line = import_prefix + files[0]
        for file_name in files[1:]:
            addition = f", {file_name}"
            current_line += addition
        lines.append(current_line)
        return "\n".join(lines)

    def _parse_paths_file(self) -> Dict[str, List[str]]:
        """
        Parse paths.py to extract service classes and their endpoint variables.

        Returns:
            Dict: Dictionary of service names mapped to lists of endpoint names.
        """
        if not self.paths_file.exists():
            return {}

        with open(self.paths_file, 'r', encoding='utf-8') as f:
            source = f.read()

        tree = ast.parse(source)
        services = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name != "Paths":
                service_name = node.name
                if service_name == "UsersProfile":
                    service_key = "profile"
                else:
                    service_key = service_name.lower()
                services[service_key] = []
                for subnode in node.body:
                    if isinstance(subnode, ast.Assign) and isinstance(subnode.targets[0], ast.Name):
                        endpoint_name = subnode.targets[0].id
                        if endpoint_name != "prefix":
                            services[service_key].append(endpoint_name)
                # Add the service prefix as an endpoint
                services[service_key].append("prefix")

        return services

    def _parse_config_file(self) -> Dict[str, Dict[str, Dict]]:
        """
        Parse config.py to extract services and their endpoint configurations.

        Returns:
            Dict: Dictionary of service names mapped to endpoint configurations (headers and params).
        """
        if not self.config_file.exists():
            return {}

        spec = importlib.util.spec_from_file_location("config", self.config_file)
        module = importlib.util.module_from_spec(spec)
        sys.modules["config"] = module
        spec.loader.exec_module(module)
        config = module.config

        services = {}
        for service_name, service in config.services.items():
            service_key = "profile" if service_name == "users_profile" else service_name
            services[service_key] = {}
            for endpoint_name, endpoint in service.endpoints.items():
                services[service_key][endpoint_name] = {
                    "headers": endpoint.headers,
                    "params": endpoint.params,
                }
        return services

    def _generate_collections_content(self, title: str) -> str:
        """Generate content for a collection file based on existing files for a specific title."""
        content = [
            "# validations",
            "",
            "# payloads",
            "",
            "# utils",
            "from partest.utils.params_manager import ParamsManager",
            "from partest.utils.headers_manager import HeadersManager",
            "# paths",
            "from src.models.endpoints.paths import Paths",
            ""
        ]

        validations_structure = self._get_service_structure(self.validations_dir)
        payloads_structure = self._get_service_structure(self.payloads_dir)
        config_structure = self._parse_config_file()
        paths_structure = self._parse_paths_file()

        # Filter for the specific title
        title_clean = self._clean_name(title.lower())
        validation_imports = []
        if title_clean in validations_structure:
            for subservice_name, files in validations_structure[title_clean].items():
                subservice_dir = subservice_name if subservice_name != "root" else title_clean
                import_path = f"src.models.validations.{title_clean}.{subservice_dir}"
                import_line = self._format_import_line(import_path, files)
                if import_line:
                    validation_imports.append(import_line)
        content[0] = "\n".join(sorted(validation_imports)) if validation_imports else "# No validation imports generated"

        payload_imports = []
        if title_clean in payloads_structure:
            for subservice_name, files in payloads_structure[title_clean].items():
                subservice_dir = subservice_name if subservice_name != "root" else title_clean
                import_path = f"src.models.payloads.{title_clean}.{subservice_dir}"
                import_line = self._format_import_line(import_path, files)
                if import_line:
                    payload_imports.append(import_line)
        content[1] = "\n".join(sorted(payload_imports)) if payload_imports else "# No payload imports generated"

        content.append("class ModelsValidations:")
        if title_clean in validations_structure:
            for subservice_name, files in validations_structure[title_clean].items():
                content.append(f"    # {title_clean}_{subservice_name}")
                for file_name in files:
                    method = file_name.split("_")[0]
                    endpoint_name = "_".join(file_name.split("_")[1:-1])
                    unique_name = f"{method}_{endpoint_name}"
                    content.append(
                        f"    {unique_name}_validation_success = {file_name}.ValidateResponseSuccess"
                    )
                    content.append(
                        f"    {unique_name}_validation_error = {file_name}.ValidateResponseError"
                    )
                content.append("")

        content.append("class ModelsPayloads:")
        if title_clean in payloads_structure:
            for subservice_name, files in payloads_structure[title_clean].items():
                content.append(f"    # {title_clean}_{subservice_name}")
                for file_name in files:
                    method = file_name.split("_")[0]
                    endpoint_name = "_".join(file_name.split("_")[1:-1])
                    unique_name = f"{method}_{endpoint_name}"
                    content.append(
                        f"    {unique_name}_payload_default = {file_name}.RequestBody().json_serialized"
                    )
                    content.append(
                        f"    {unique_name}_payload_req = {file_name}.RequestBody.get_json_required()"
                    )
                    content.append(
                        f"    {unique_name}_payload_req_fields = {file_name}.RequestBody.get_required_fields()"
                    )
                    if method in ["put", "post"] and endpoint_name in ["addressId"]:
                        content.append(
                            f"    {unique_name}_payload_env = {file_name}.RequestBody.get_env_fields()"
                        )
                content.append("")

        content.append("    # methods_miss_req")
        if title_clean in payloads_structure:
            for subservice_name, files in payloads_structure[title_clean].items():
                for file_name in files:
                    method = file_name.split("_")[0]
                    endpoint_name = "_".join(file_name.split("_")[1:-1])
                    unique_name = f"{method}_{subservice_name}_{endpoint_name}"
                    content.append(
                        f"    @staticmethod\n"
                        f"    def parametrize_req_{unique_name}_payload(req):\n"
                        f"        return {file_name}.RequestBody.get_json_miss_required(req)\n"
                    )
        content.append("")

        content.append("class ModelsPaths:")
        for service_name, endpoints in sorted(paths_structure.items()):
            class_name = service_name.capitalize() if service_name != "profile" else "UsersProfile"
            # Add service prefix as an endpoint
            content.append(f"    {service_name} = Paths.{class_name}.prefix")
            for endpoint_name in sorted(endpoints):
                if endpoint_name != "prefix":  # Skip prefix as it's already added
                    unique_name = f"{service_name}_{endpoint_name}"
                    content.append(f"    {unique_name} = Paths.{class_name}.{endpoint_name}")
        content.append("")

        content.append(
            "class ModelsHeaders:\n"
            "    def __init__(self, token: str):\n"
            "        self._headers_manager = HeadersManager(token=token)\n"
            '        self.base = {"Authorization": f"Bearer {token}"}\n'
            "        self.auth = self.get_headers()\n"
        )
        for service_name in sorted(config_structure.keys()):
            has_headers = any(
                config["headers"]
                for endpoint_name, config in config_structure[service_name].items()
            )
            if has_headers:
                attr_name = service_name
                content.append(f"        self.{attr_name} = self.get_headers('{service_name}')")
        content.append(
            "\n"
            "    def get_headers(self, endpoint: str = None):\n"
            "        if endpoint:\n"
            "            return self._headers_manager.generate_headers('user', endpoint)\n"
            "        return self.base\n"
        )
        content.append("")

        content.append(
            "class ModelsParams:\n"
            "    def __init__(self):\n"
            "        self._params_manager = ParamsManager()\n"
        )
        for service_name in sorted(config_structure.keys()):
            for endpoint_name, config in sorted(config_structure[service_name].items()):
                if config["params"]:
                    attr_name = (
                        f"{service_name}_{endpoint_name}"
                        if endpoint_name != "root"
                        else service_name
                    )
                    content.append(f"        self.{attr_name} = self.get_params('{service_name}_{endpoint_name}')")
        content.append(
            "\n"
            "    def get_params(self, endpoint: str = None):\n"
            "        if endpoint:\n"
            "            return self._params_manager.generate_params('user', endpoint)\n"
            "        return {}\n"
        )
        content.append("")

        content.append(
            "class PagesModels:\n"
            "    def __init__(self):\n"
            "        self.validate = ModelsValidations()\n"
            "        self.payload = ModelsPayloads()\n"
            "        self.paths = ModelsPaths()\n"
            "        self.headers = ModelsHeaders(token='')\n"
            "        self.params = ModelsParams()\n"
        )

        return "\n".join(content)

    def _generate_collection_file(self) -> List[CollectionFile]:
        """Generate collection files based on existing files for each title."""
        collections = []
        validations_structure = self._get_service_structure(self.validations_dir)
        titles = sorted(validations_structure.keys())

        for title in titles:
            collections_content = self._generate_collections_content(title)
            collection_file = CollectionFile(
                name=f"{title.lower()}_collection.py",
                content=collections_content
            )
            collections.append(collection_file)

        return collections

    def get_files(self) -> List[CollectionFile]:
        """Return the list of collection files."""
        return self.files

    def get_file_by_name(self, name: str) -> CollectionFile:
        """Retrieve a collection file by its name."""
        for file in self.files:
            if file.name == name:
                return file
        return None