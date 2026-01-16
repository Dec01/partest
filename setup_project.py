import os
import datetime
from pathlib import Path
import sys
from partest.project_gen.new_parparser import SwaggerSettings
from partest.project_gen.root_files import RootFilesContainer
from partest.project_gen.models_endpoints import EndpointsContainer
from partest.project_gen.models_validates import ValidationsContainer
from partest.project_gen.models_payloads import PayloadsContainer
from partest.project_gen.models_collections import CollectionsContainer
from partest.project_gen.models_tests import TestsContainer

def create_project_structure(swagger_files, project_root="projects-gen"):
    """
    Creates a project structure for autotests and generates api_reference.json.

    Args:
        swagger_files (dict): Dictionary of Swagger files {name: (source_type, path)}.
        project_root (str): Root directory for generated projects.
    """
    # Create project directory with timestamp
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    project_dir = Path(project_root) / f"project_{timestamp}"
    project_dir.mkdir(parents=True, exist_ok=True)

    # Define project structure (excluding endpoints, which will be generated)
    structure = {
        "src": {
            "models": {
            },
            "tests": {
            },
            "utils": {
                "response_timer.py": "# Utility for measuring API response time\n",
                "compare_stands.py": "# Utility for comparing stand performance\n"
            }
        }
    }

    # Create directory structure and files
    def create_structure(base_path, structure_dict):
        for name, content in structure_dict.items():
            path = base_path / name
            if isinstance(content, dict):
                path.mkdir(exist_ok=True)
                create_structure(path, content)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)

    # Create project structure
    create_structure(project_dir, structure)

    # Create root files from RootFilesContainer
    root_files_container = RootFilesContainer()
    for root_file in root_files_container.get_files():
        with open(project_dir / root_file.name, "w", encoding="utf-8") as f:
            f.write(root_file.content)

    # Generate api_reference.json
    api_reference_path = project_dir / "api_reference.json"
    try:
        swagger_settings = SwaggerSettings(swagger_files)
        api_reference = swagger_settings.generate_api_reference(output_file=str(api_reference_path))
        print(f"Generated api_reference.json in {project_dir}")
    except Exception as e:
        print(f"Failed to generate api_reference.json: {e}")
        sys.exit(1)

    # Create endpoint files from EndpointsContainer
    endpoints_container = EndpointsContainer(str(api_reference_path))
    endpoints_dir = project_dir / "src" / "models" / "endpoints"
    endpoints_dir.mkdir(exist_ok=True)
    for endpoint_file in endpoints_container.get_files():
        with open(endpoints_dir / endpoint_file.name, "w", encoding="utf-8") as f:
            f.write(endpoint_file.content)

    print(f"Project structure created successfully at {project_dir}")

    # Create validations files from ValidationsContainer
    validations_container = ValidationsContainer(str(api_reference_path))
    validations_base_dir = project_dir / "src" / "models" / "validations"
    validations_base_dir.mkdir(parents=True, exist_ok=True)
    for validation_file in validations_container.get_files():
        file_path = validations_base_dir / validation_file.name
        print(f"Attempting to create validation file: {file_path}")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(validation_file.content)

    print(f"Project structure created successfully at {project_dir}")

    # Create payload files from PayloadsContainer
    payloads_container = PayloadsContainer(str(api_reference_path))
    payloads_base_dir = project_dir / "src" / "models" / "payloads"
    payloads_base_dir.mkdir(parents=True, exist_ok=True)
    for payload_file in payloads_container.get_files():
        file_path = payloads_base_dir / payload_file.name
        print(f"Attempting to create payload file: {file_path}")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(payload_file.content)

    print(f"Project structure created successfully at {project_dir}")

    # Create collections files from CollectionsContainer
    collections_container = CollectionsContainer(str(project_dir))
    collections_dir = project_dir / "src" / "models" / "collections"
    collections_dir.mkdir(exist_ok=True)
    collection_titles = []
    for collection_file in collections_container.get_files():
        file_path = collections_dir / collection_file.name
        print(f"Attempting to create collection file: {file_path}")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(collection_file.content)
        # Extract title from filename (e.g., 'Users' from 'Users_collection.py')
        title = collection_file.name.replace('_collection.py', '').lower()
        collection_titles.append(title)

    # Create collections_manager.py
    manager_content = []
    for title in sorted(collection_titles):
        title_clean = title.replace('_', '')
        manager_content.append(f"from src.models.collections.{title}_collection import PagesModels as {title_clean.capitalize()}PagesModels")
    manager_content.append("")
    manager_content.append("class ModelsManager:")
    manager_content.append("    def __init__(self):")
    for title in sorted(collection_titles):
        title_clean = title.replace('_', '')
        manager_content.append(f"        self.{title_clean} = {title_clean.capitalize()}PagesModels()")
    manager_content.append("")
    manager_content.append("models = ModelsManager()")
    manager_content = "\n".join(manager_content)

    manager_file_path = collections_dir / "collections_manager.py"
    print(f"Attempting to create collections manager file: {manager_file_path}")
    with open(manager_file_path, "w", encoding="utf-8") as f:
        f.write(manager_content)

    print(f"Project structure created successfully at {project_dir}")

    # Create test files from TestsContainer
    tests_container = TestsContainer(str(api_reference_path))
    tests_base_dir = project_dir / "src" / "tests"
    tests_base_dir.mkdir(parents=True, exist_ok=True)
    for test_file in tests_container.get_files():
        file_path = tests_base_dir / test_file.name
        print(f"Attempting to create test file: {file_path}")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(test_file.content)

    print(f"Project structure created successfully at {project_dir}")

    # Create __init__.py files in all directories
    def create_init_files(base_path):
        """Recursively create __init__.py files in all directories with appropriate imports."""
        for root, dirs, files in os.walk(base_path):
            current_dir = Path(root)
            # Skip if __init__.py already exists to avoid overwriting
            init_file = current_dir / "__init__.py"
            if not init_file.exists():
                init_content = []
                # Add imports for subdirectories
                for dir_name in sorted(dirs):
                    init_content.append(f"from .{dir_name} import *")
                # Add imports for Python files (excluding __init__.py itself)
                for file_name in sorted(files):
                    if file_name.endswith(".py") and file_name != "__init__.py":
                        module_name = file_name[:-3]  # Remove .py extension
                        init_content.append(f"from .{module_name} import *")
                # Write __init__.py if there are imports to add
                if init_content:
                    with open(init_file, "w", encoding="utf-8") as f:
                        f.write("\n".join(init_content) + "\n")
                    print(f"Created __init__.py in {current_dir}")

    # Call function to create __init__.py files
    create_init_files(project_dir)
    print(f"__init__.py files created in all directories under {project_dir}")

if __name__ == "__main__":
    # Example usage: specify your Swagger files here
    swagger_files = {
        "api": ("local", "C:\\src\\projects\\partest\\app-openapi.yaml")  # Replace with actual path
    }
    create_project_structure(swagger_files)