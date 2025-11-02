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
    """

    id: str
    max_turns: int = 20
    expected_tools: List[str] = None

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
        """Return mock configuration for this task.

        Override this method to provide mock responses for AWS APIs
        or other external services used by the MCP server.

        Returns:
            Mock configuration dictionary or None

        Example:
            return {
                'boto3': {
                    'cloudwatch': {
                        'GetMetricData': {
                            'MetricDataResults': [...]
                        },
                        'DescribeAlarms': 'fixtures/cloudwatch/alarms.json'
                    }
                }
            }
        """
        return None

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
