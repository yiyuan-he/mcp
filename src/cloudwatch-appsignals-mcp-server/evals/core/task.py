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
from dataclasses import dataclass, field
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
        mocks: Optional mock configuration for AWS APIs or other external services
        fixtures_dir: Base directory for resolving relative fixture paths (None = no path resolution)
    """

    id: str
    max_turns: int = 20
    expected_tools: List[str] = None
    mocks: Optional[Dict[str, Any]] = None
    fixtures_dir: Optional[Path] = None

    def __post_init__(self):
        """Initialize expected_tools to empty list if None."""
        if self.expected_tools is None:
            self.expected_tools = []

    @abstractmethod
    def get_prompts(self, context: Dict[str, Any]) -> list[str]:
        """Return task prompt(s) to send to the agent.

        Always returns a list, even for single prompts. Multiple prompts
        will be sent sequentially to the agent.

        Args:
            context: Runtime context dictionary with keys:
                - working_directory: Path to working directory for this task
                - bedrock_client: Boto3 Bedrock client

        Returns:
            List of prompts to send sequentially

        Example:
            # Simple prompt (ignores context)
            def get_prompts(self, context):
                return ["List services with high latency"]

            # Complex prompt (uses context for paths)
            def get_prompts(self, context):
                working_dir = context['working_directory']
                path = working_dir / self.iac_dir
                return [f"Enable Application Signals at {path}"]
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

    def get_mocks(self) -> Optional[dict]:
        """Return mock configuration for this task with resolved fixture paths.

        This method handles path resolution automatically. Subclasses should
        pass mock configuration via the `mocks` parameter in __init__ instead
        of overriding this method.

        Returns:
            Mock configuration dictionary with resolved paths, or None

        Raises:
            ValueError: If mocks contain fixture file references but fixtures_dir is not specified

        Example task definition:
            Task(
                id='my_task',
                fixtures_dir=Path('/path/to/fixtures'),
                mocks={
                    'boto3': {
                        'application-signals': {
                            'list_audit_findings': 'list_audit_findings/healthy.json',
                            'get_service_level_objective': [
                                'get_service_level_objective/slo1.json',
                                'get_service_level_objective/slo2.json'
                            ]
                        }
                    }
                }
            )
        """
        if not self.mocks:
            return None

        # If mocks exist but no fixtures_dir, validate that we don't have fixture references
        if self.fixtures_dir is None:
            if self._has_fixture_references(self.mocks):
                raise ValueError(
                    f"Task '{self.id}' has fixture file references in mocks but no fixtures_dir specified. "
                    f"Either provide fixtures_dir parameter or use absolute paths/inline mock data."
                )
            # No fixture files, just return as-is (inline mocks or absolute paths)
            return self.mocks

        # Resolve fixture paths relative to fixtures directory
        return self._resolve_fixture_paths(self.mocks, self.fixtures_dir)

    def _has_fixture_references(self, mocks: Dict[str, Any]) -> bool:
        """Check if mocks contain relative fixture file references.

        Args:
            mocks: Mock configuration dictionary

        Returns:
            True if any value looks like a relative fixture file path
        """
        for key, value in mocks.items():
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

    def _resolve_fixture_paths(self, mocks: Dict[str, Any], fixtures_dir: Path) -> Dict[str, Any]:
        """Recursively resolve fixture file paths to absolute paths.

        Args:
            mocks: Mock configuration dictionary
            fixtures_dir: Base directory for fixture files

        Returns:
            Mock configuration with resolved paths
        """
        resolved = {}
        for key, value in mocks.items():
            if isinstance(value, dict):
                # Recursively resolve nested dictionaries
                resolved[key] = self._resolve_fixture_paths(value, fixtures_dir)
            elif isinstance(value, list):
                # Lists should contain request/response pairs
                resolved[key] = [self._resolve_request_response_pair(item, fixtures_dir) for item in value]
            else:
                # Pass through other values
                resolved[key] = value
        return resolved

    def _resolve_request_response_pair(self, pair: Dict[str, Any], fixtures_dir: Path) -> Dict[str, Any]:
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

        return {
            'request': pair['request'],
            'response': response
        }

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
