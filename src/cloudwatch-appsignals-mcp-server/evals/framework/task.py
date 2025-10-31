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
from typing import Optional


@dataclass
class Task(ABC):
    """Base class for evaluation tasks.

    Subclasses must implement get_prompt() and rubric property to define
    the task prompt(s) and validation criteria.

    Attributes:
        id: Unique identifier for the task
        max_turns: Maximum conversation turns allowed (default: 20)
    """

    id: str
    max_turns: int = 20

    @abstractmethod
    def get_prompt(self) -> list[str]:
        """Return task prompt(s) to send to the agent.

        Always returns a list, even for single prompts. Multiple prompts
        will be sent sequentially to the agent.

        Returns:
            List of prompts to send sequentially

        Example:
            # Single prompt
            return ["Enable Application Signals for Flask app"]

            # Multiple prompts for sequential interaction
            return [
                "What services have high latency?",
                "Check the database metrics",
                "What's the root cause?"
            ]
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

    def __str__(self) -> str:
        """String representation of the task."""
        return f"Task({self.id})"
