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

"""Captors for capturing agent behavior and outputs.

Captors extract specific information from agent execution:
- GitDiffCaptor: Captures file changes via git diff
- ToolCallsCaptor: Captures tool invocation sequence
- ConversationCaptor: Captures full conversation history
- FinalResponseCaptor: Captures agent's final response
- ToolResultsCaptor: Captures tool execution results
"""

from .process_executor import ProcessExecutor, SubprocessExecutor
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List


class Captor(ABC):
    """Base class for capturing agent outputs.

    Captors are responsible for extracting specific information
    from agent execution for later validation.
    """

    @abstractmethod
    def capture(
        self,
        messages: List[Dict[str, Any]],
        metrics_tracker: Any,
        project_root: Path,
    ) -> Dict[str, Any]:
        """Capture output from agent execution.

        Args:
            messages: Conversation history from agent loop
            metrics_tracker: Metrics tracker instance
            project_root: Project root directory

        Returns:
            Dictionary containing captured data
        """
        pass


class GitDiffCaptor(Captor):
    """Captures git diff of file changes made by agent.

    Useful for validating code modification tasks.
    """

    def __init__(self, git_paths: List[str], process_executor: ProcessExecutor = None):
        """Initialize GitDiffCaptor.

        Args:
            git_paths: List of paths (relative to mcp_repo_root) to capture git diff for
            process_executor: Optional ProcessExecutor instance. If not provided, uses SubprocessExecutor.
        """
        self.git_paths = git_paths
        self.process_executor = process_executor if process_executor is not None else SubprocessExecutor()

    def capture(
        self,
        messages: List[Dict[str, Any]],
        metrics_tracker: Any,
        project_root: Path,
    ) -> Dict[str, Any]:
        """Capture git diff.

        Args:
            messages: Conversation history (unused)
            metrics_tracker: Metrics tracker (unused)
            project_root: MCP repository root (combined with git_paths to get full paths)

        Returns:
            Dictionary with 'git_diff' key containing diff string
        """
        try:
            # Build full paths from mcp_repo_root + git_paths
            full_paths = [str(project_root / path) for path in self.git_paths]

            # Run git diff with path arguments to limit changes to specified paths
            result = self.process_executor.run(
                ['git', 'diff', '--'] + full_paths,
                timeout=10,
            )
            return {'git_diff': result.stdout}
        except Exception as e:
            return {'git_diff': '', 'error': str(e)}


class ToolCallsCaptor(Captor):
    """Captures sequence of tool calls made by agent.

    Useful for validating workflow and tool usage patterns.
    """

    def capture(
        self,
        messages: List[Dict[str, Any]],
        metrics_tracker: Any,
        project_root: Path,
    ) -> Dict[str, Any]:
        """Capture tool call sequence.

        Args:
            messages: Conversation history to extract tool calls from
            metrics_tracker: Metrics tracker (unused)
            project_root: Project root (unused)

        Returns:
            Dictionary with 'tool_calls' key containing list of tool calls
        """
        tool_calls = []

        for message in messages:
            if message.get('role') == 'assistant':
                for content in message.get('content', []):
                    if 'toolUse' in content:
                        tool_use = content['toolUse']
                        tool_calls.append(
                            {
                                'name': tool_use['name'],
                                'input': tool_use.get('input', {}),
                            }
                        )

        return {'tool_calls': tool_calls}


class ConversationCaptor(Captor):
    """Captures full conversation history.

    Useful for detailed analysis of agent behavior.
    """

    def capture(
        self,
        messages: List[Dict[str, Any]],
        metrics_tracker: Any,
        project_root: Path,
    ) -> Dict[str, Any]:
        """Capture full conversation.

        Args:
            messages: Conversation history
            metrics_tracker: Metrics tracker (unused)
            project_root: Project root (unused)

        Returns:
            Dictionary with 'conversation' key containing messages
        """
        return {'conversation': messages}


class FinalResponseCaptor(Captor):
    """Captures agent's final text response.

    Useful for validating data interpretation tasks where the
    agent should provide a summary or answer.
    """

    def capture(
        self,
        messages: List[Dict[str, Any]],
        metrics_tracker: Any,
        project_root: Path,
    ) -> Dict[str, Any]:
        """Capture final response text.

        Args:
            messages: Conversation history
            metrics_tracker: Metrics tracker (unused)
            project_root: Project root (unused)

        Returns:
            Dictionary with 'final_response' key containing text
        """
        # Find last assistant message with text content
        for message in reversed(messages):
            if message.get('role') == 'assistant':
                for content in message.get('content', []):
                    if 'text' in content:
                        return {'final_response': content['text']}

        return {'final_response': '', 'error': 'No final response found'}


class ToolResultsCaptor(Captor):
    """Captures results from tool executions.

    Useful for validating that tools returned expected data.
    """

    def capture(
        self,
        messages: List[Dict[str, Any]],
        metrics_tracker: Any,
        project_root: Path,
    ) -> Dict[str, Any]:
        """Capture tool results.

        Args:
            messages: Conversation history
            metrics_tracker: Metrics tracker (unused)
            project_root: Project root (unused)

        Returns:
            Dictionary with 'tool_results' key containing list of results
        """
        tool_results = []

        for message in messages:
            if message.get('role') == 'user':
                for content in message.get('content', []):
                    if 'toolResult' in content:
                        tool_result = content['toolResult']
                        result_content = tool_result.get('content', [])
                        result_text = ''
                        if result_content:
                            result_text = result_content[0].get('text', '')

                        tool_results.append(
                            {
                                'toolUseId': tool_result.get('toolUseId'),
                                'content': result_text,
                            }
                        )

        return {'tool_results': tool_results}
