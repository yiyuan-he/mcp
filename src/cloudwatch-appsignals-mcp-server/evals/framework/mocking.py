# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Mocking system for MCP evaluation framework.

Provides extensible mocking for external dependencies (boto3, requests, etc.)
used by MCP servers during evaluation.
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock


class MockHandler(ABC):
    """Base class for library-specific mock handlers.

    Subclasses implement patching logic for specific libraries
    (e.g., boto3, requests, database clients).
    """

    @abstractmethod
    def get_library_name(self) -> str:
        """Return the name of the library this handler mocks.

        Returns:
            Library name (e.g., 'boto3', 'requests')
        """
        pass

    @abstractmethod
    def patch(self, mock_config: Dict[str, Any], fixtures_dir: Optional[Path] = None) -> None:
        """Apply patches to the library.

        Args:
            mock_config: Mock configuration dictionary for this library
            fixtures_dir: Directory containing fixture files
        """
        pass

    @abstractmethod
    def unpatch(self) -> None:
        """Remove all patches applied by this handler."""
        pass

    def resolve_fixture(self, value: Any, fixtures_dir: Optional[Path] = None) -> Any:
        """Resolve fixture references to actual data.

        If value is a string path to a JSON file, load and return it.
        Otherwise return value as-is.

        Args:
            value: Value that may be a fixture reference
            fixtures_dir: Directory containing fixture files

        Returns:
            Resolved fixture data or original value
        """
        if isinstance(value, str) and (value.endswith('.json') or value.endswith('.txt')):
            if fixtures_dir:
                fixture_path = fixtures_dir / value
            else:
                # Assume relative to current directory
                fixture_path = Path(value)

            if fixture_path.exists():
                if value.endswith('.json'):
                    with open(fixture_path, 'r') as f:
                        return json.load(f)
                else:
                    with open(fixture_path, 'r') as f:
                        return f.read()

        return value


class Boto3MockHandler(MockHandler):
    """Mock handler for boto3 clients.

    Patches boto3.client() to return mocked clients with predefined responses.
    """

    def __init__(self):
        self.original_client = None
        self.mock_responses: Dict[str, Dict[str, Any]] = {}
        self.fixtures_dir: Optional[Path] = None

    def get_library_name(self) -> str:
        """Return library name."""
        return 'boto3'

    def patch(self, mock_config: Dict[str, Any], fixtures_dir: Optional[Path] = None) -> None:
        """Patch boto3.client() to return mocked clients.

        Args:
            mock_config: Dict mapping service names to operation responses
                Example: {'cloudwatch': {'GetMetricData': {...}}}
            fixtures_dir: Directory containing fixture files
        """
        import boto3

        self.fixtures_dir = fixtures_dir
        self.original_client = boto3.client

        # Resolve fixtures in mock config
        resolved_config = {}
        for service, operations in mock_config.items():
            resolved_config[service] = {}
            for operation, response in operations.items():
                resolved_config[service][operation] = self.resolve_fixture(response, fixtures_dir)

        self.mock_responses = resolved_config

        # Patch boto3.client
        boto3.client = self._create_mock_client

    def unpatch(self) -> None:
        """Restore original boto3.client."""
        if self.original_client:
            import boto3

            boto3.client = self.original_client
            self.original_client = None
            self.mock_responses = {}

    def _create_mock_client(self, service_name: str, **kwargs):
        """Create a mocked boto3 client.

        Args:
            service_name: AWS service name (e.g., 'cloudwatch')
            **kwargs: Additional client parameters (ignored)

        Returns:
            Mocked client with predefined responses
        """
        mock_client = MagicMock()

        if service_name in self.mock_responses:
            service_mocks = self.mock_responses[service_name]

            # Set up each operation as a mock method
            for operation, response_data in service_mocks.items():
                # Handle sequential responses (list of responses)
                if isinstance(response_data, list):
                    mock_method = MagicMock(side_effect=response_data)
                else:
                    mock_method = MagicMock(return_value=response_data)

                # Convert operation name to method name (PascalCase to snake_case for some SDKs)
                setattr(mock_client, operation, mock_method)

        return mock_client


class MockHandlerRegistry:
    """Registry for mock handlers.

    Provides centralized management and discovery of available mock handlers.
    """

    def __init__(self):
        self._handlers: Dict[str, MockHandler] = {}
        self._register_builtin_handlers()

    def _register_builtin_handlers(self):
        """Register built-in mock handlers."""
        self.register(Boto3MockHandler())

    def register(self, handler: MockHandler):
        """Register a mock handler.

        Args:
            handler: MockHandler instance
        """
        library_name = handler.get_library_name()
        self._handlers[library_name] = handler

    def get_handler(self, library_name: str) -> Optional[MockHandler]:
        """Get handler for a library.

        Args:
            library_name: Name of library (e.g., 'boto3')

        Returns:
            MockHandler instance or None if not found
        """
        return self._handlers.get(library_name)

    def list_supported_libraries(self) -> list[str]:
        """List all supported mock libraries.

        Returns:
            List of library names
        """
        return list(self._handlers.keys())

    def patch_all(self, mock_config: Dict[str, Any], fixtures_dir: Optional[Path] = None) -> None:
        """Apply all mocks from configuration.

        Args:
            mock_config: Full mock configuration dict
            fixtures_dir: Directory containing fixture files
        """
        for library_name, library_config in mock_config.items():
            handler = self.get_handler(library_name)
            if handler:
                handler.patch(library_config, fixtures_dir)
            else:
                raise ValueError(
                    f"No mock handler registered for '{library_name}'. "
                    f'Supported libraries: {", ".join(self.list_supported_libraries())}'
                )

    def unpatch_all(self) -> None:
        """Remove all patches."""
        for handler in self._handlers.values():
            handler.unpatch()


# Global registry instance
_registry = MockHandlerRegistry()


def get_registry() -> MockHandlerRegistry:
    """Get the global mock handler registry.

    Returns:
        MockHandlerRegistry instance
    """
    return _registry
