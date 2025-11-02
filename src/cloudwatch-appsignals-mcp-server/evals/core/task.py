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

"""Base Task class for MCP evaluations.

Tasks define what the agent should accomplish, validation criteria,
and optional mock configurations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Task(ABC):
    """Base class for evaluation tasks.

    Subclasses must implement get_prompts() and rubric property to define
    the task prompt(s) and validation criteria.

    Context dictionary contains runtime information:
        - working_directory: Path to working directory for this task
        - bedrock_client: Boto3 Bedrock client (for validators)

    Attributes:
        id: Unique identifier for the task
        max_turns: Maximum conversation turns allowed (default: 20)
        expected_tools: List of MCP tool names expected to be called (for hit rate metric)
        mock_config: Optional mock configuration for AWS APIs or other external services (raw, with relative paths)
        fixtures_dir: Base directory for resolving relative fixture paths (None = no path resolution)
    """

    id: str
    max_turns: int = 20
    expected_tools: List[str] = None
    mock_config: Optional[Dict[str, Any]] = None
    fixtures_dir: Optional[Path] = None

    def __post_init__(self):
        """Initialize expected_tools to empty list if None."""
        if self.expected_tools is None:
            self.expected_tools = []

    @abstractmethod
    def get_prompt(self, context: Dict[str, Any]) -> str:
        """Return task prompt to send to the agent.

        Args:
            context: Runtime context dictionary with keys:
                - working_directory: Path to working directory for this task
                - bedrock_client: Boto3 Bedrock client

        Returns:
            Prompt string to send to agent

        Example:
            # Simple prompt (ignores context)
            def get_prompt(self, context):
                return "List services with high latency"

            # Complex prompt (uses context for paths)
            def get_prompt(self, context):
                working_dir = context['working_directory']
                path = working_dir / self.iac_dir
                return f"Enable Application Signals at {path}"
        """
        pass

    @property
    @abstractmethod
    def rubric(self) -> list[str]:
        """Return validation criteria for this task.

        Returns:
            List of validation criteria strings

        Example:
            return [
                "Code compiles without errors",
                "Application Signals is enabled correctly",
                "All required configuration files are created"
            ]
        """
        pass

    def get_captors(self, context: Dict[str, Any]) -> List[Any]:
        """Return captors for this task.

        Override this method to specify what data to capture from agent execution.

        Args:
            context: Runtime context dictionary

        Returns:
            List of Captor instances

        Example:
            from framework import GitDiffCaptor
            return [GitDiffCaptor(git_paths=self.paths)]
        """
        return []

    def get_validators(self, context: Dict[str, Any]) -> List[Any]:
        """Return validators for this task.

        Override this method to specify how to validate task completion.

        Args:
            context: Runtime context dictionary with keys:
                - working_directory: Path to working directory for this task
                - bedrock_client: Boto3 Bedrock client

        Returns:
            List of Validator instances

        Example:
            from evals.core import BuildValidator, LLMJudgeValidator
            return [
                BuildValidator(command="npm run build", working_dir=...),
                LLMJudgeValidator(validation_prompt_template=...)
            ]
        """
        return []

    @property
    def resolved_mock_config(self) -> Optional[dict]:
        """Mock configuration with all fixture paths resolved to absolute paths.

        This property automatically resolves relative fixture file paths to absolute
        paths based on the fixtures_dir. This is what should be passed to the
        mocking system at runtime.

        Returns:
            Mock configuration dictionary with resolved absolute paths, or None

        Raises:
            ValueError: If mock_config contains fixture file references but fixtures_dir is not specified

        Example:
            # Task definition with relative paths:
            task = Task(
                id='my_task',
                fixtures_dir=Path('/project/fixtures'),
                mock_config={
                    'boto3': {
                        'application-signals': {
                            'list_services': [
                                {'request': {}, 'response': 'services.json'}
                            ]
                        }
                    }
                }
            )

            # Access resolved mock config:
            task.resolved_mock_config
            # Returns:
            # {
            #     'boto3': {
            #         'application-signals': {
            #             'list_services': [
            #                 {'request': {}, 'response': '/project/fixtures/services.json'}
            #             ]
            #         }
            #     }
            # }
        """
        if not self.mock_config:
            return None

        # If mock_config exists but no fixtures_dir, validate that we don't have fixture references
        if self.fixtures_dir is None:
            if self._has_fixture_references(self.mock_config):
                raise ValueError(
                    f"Task '{self.id}' has fixture file references in mock_config but no fixtures_dir specified. "
                    f'Either provide fixtures_dir parameter or use absolute paths/inline mock data.'
                )
            # No fixture files, just return as-is (inline mock config or absolute paths)
            return self.mock_config

        # Resolve fixture paths relative to fixtures directory
        return self._resolve_fixture_paths(self.mock_config, self.fixtures_dir)

    def _has_fixture_references(self, mock_config: Dict[str, Any]) -> bool:
        """Check if mock configuration contains relative fixture file references.

        Args:
            mock_config: Mock configuration dictionary

        Returns:
            True if any value looks like a relative fixture file path
        """
        for key, value in mock_config.items():
            if isinstance(value, dict):
                if self._has_fixture_references(value):
                    return True
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and (item.endswith('.json') or item.endswith('.txt')):
                        # Check if it looks like a relative path (not absolute)
                        if not Path(item).is_absolute():
                            return True
            elif isinstance(value, str) and (value.endswith('.json') or value.endswith('.txt')):
                # Check if it looks like a relative path (not absolute)
                if not Path(value).is_absolute():
                    return True
        return False

    def _resolve_fixture_paths(self, mock_config: Dict[str, Any], fixtures_dir: Path) -> Dict[str, Any]:
        """Recursively resolve fixture file paths to absolute paths.

        Args:
            mock_config: Mock configuration dictionary
            fixtures_dir: Base directory for fixture files

        Returns:
            Mock configuration with resolved paths
        """
        resolved = {}
        for key, value in mock_config.items():
            if isinstance(value, dict):
                # Recursively resolve nested dictionaries
                resolved[key] = self._resolve_fixture_paths(value, fixtures_dir)
            elif isinstance(value, list):
                # Lists should contain request/response pairs
                resolved[key] = [
                    self._resolve_request_response_pair(item, fixtures_dir) for item in value
                ]
            else:
                # Pass through other values
                resolved[key] = value
        return resolved

    def _resolve_request_response_pair(
        self, pair: Dict[str, Any], fixtures_dir: Path
    ) -> Dict[str, Any]:
        """Resolve a request/response pair.

        Args:
            pair: Dict with 'request' and 'response' keys
            fixtures_dir: Base directory for fixture files

        Returns:
            Resolved pair with absolute response path
        """
        if not isinstance(pair, dict) or 'request' not in pair or 'response' not in pair:
            raise ValueError(
                f"Expected request/response pair dict with 'request' and 'response' keys, got: {pair}"
            )

        response = pair['response']
        # Resolve response path if it's a string fixture reference
        if isinstance(response, str) and (response.endswith('.json') or response.endswith('.txt')):
            response = str(fixtures_dir / response)

        return {'request': pair['request'], 'response': response}

    def get_working_directory(self) -> Optional[Path]:
        """Return the working directory for this task.

        Override this method to specify a working directory where the task
        should operate (e.g., path to samples/ for enablement tasks).

        Returns:
            Path to working directory, or None to use current directory

        Example:
            def get_working_directory(self):
                # Return path to samples directory for enablement tasks
                return Path(__file__).parent.parent.parent.parent / 'samples'
        """
        return None

    @abstractmethod
    def get_server_file(self) -> Path:
        """Return the path to the MCP server file.

        Returns:
            Path to server.py file

        Example:
            def get_server_file(self):
                return Path(__file__).parent.parent.parent / 'awslabs' / 'cloudwatch_appsignals_mcp_server' / 'server.py'
        """
        pass

    @abstractmethod
    def get_server_root_directory(self) -> Path:
        """Return the root directory of the MCP server.

        This is the directory where the server should run from (where its imports work).

        Returns:
            Path to server root directory

        Example:
            def get_server_root_directory(self):
                # For server at: cloudwatch-appsignals-mcp-server/awslabs/cloudwatch_appsignals_mcp_server/server.py
                # Return: cloudwatch-appsignals-mcp-server/ directory
                return Path(__file__).parent.parent.parent
        """
        pass

    def cleanup(self, context: Dict[str, Any]) -> None:
        """Clean up after task execution.

        Override this method to perform cleanup (e.g., reset git state).

        Args:
            context: Runtime context dictionary with keys:
                - working_directory: Path to working directory
        """
        pass

    def __str__(self) -> str:
        """String representation of the task."""
        return f'Task({self.id})'
