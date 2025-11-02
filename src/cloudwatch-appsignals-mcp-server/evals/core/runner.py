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

"""Evaluation runner orchestrating task execution and validation.

EvalRunner coordinates:
- MCP server connection with optional mocking
- Task execution orchestration
- Result reporting

Heavy lifting delegated to:
- PromptExecutor: Executes individual prompts with agent loop, captors, validators
"""

from .executor import PromptExecutor
from .mcp_client import connect_to_mcp_server
from .task import Task
from loguru import logger
from mcp import ClientSession
from pathlib import Path
from typing import Any, Dict, List


class EvalRunner:
    """Orchestrates evaluation of MCP tools using agent-based testing.

    Example:
        # Define tasks
        tasks = [
            EnablementTask(id='ec2_python', ...),
            DataInterpretationTask(id='analyze_metrics', ...),
        ]

        # Run evaluations
        runner = EvalRunner(tasks, server_path='../../src/server.py')
        results = await runner.run_all(bedrock_client, verbose=True)
    """

    def __init__(self, tasks: List[Task]):
        """Initialize evaluation runner.

        Args:
            tasks: List of Task instances to evaluate
        """
        self.tasks = tasks

        # Initialize helper classes (Dependency Injection)
        # These could be passed in as parameters for even better testability,
        # but for now we instantiate them here
        self.prompt_executor = PromptExecutor()

    async def run_all(
        self,
        bedrock_client: Any,
        verbose: bool = False,
        mcp_repo_root: Path = None,
    ) -> List[Dict[str, Any]]:
        """Run all tasks and return results.

        Args:
            bedrock_client: Boto3 Bedrock Runtime client
            verbose: Enable verbose logging
            mcp_repo_root: MCP repository root directory (defaults to cwd)

        Returns:
            List of result dictionaries, one per task
        """
        if mcp_repo_root is None:
            mcp_repo_root = Path.cwd()

        results = []

        # Connect to MCP server once for all tasks
        # Note: We connect per-task if mocks differ, otherwise reuse connection
        for task in self.tasks:
            logger.info(f'Running task: {task.id}')

            try:
                result = await self.run_task(task, bedrock_client, verbose, mcp_repo_root)
                results.append(result)
            except Exception as e:
                logger.error(f'Task {task.id} failed: {e}')
                results.append({'task_id': task.id, 'error': str(e), 'success': False})

        return results

    async def run_task(
        self,
        task: Task,
        bedrock_client: Any,
        verbose: bool,
        working_directory: Path,
    ) -> Dict[str, Any]:
        """Run a single task.

        This method orchestrates the high-level flow:
        1. Connect to MCP server
        2. Execute the prompt (delegated to PromptExecutor)

        The actual work is delegated to focused helper classes, making this
        method easy to understand and maintain.

        Args:
            task: Task instance
            bedrock_client: Boto3 Bedrock Runtime client
            verbose: Enable verbose logging
            working_directory: Working directory for this task

        Returns:
            Result dictionary with validation and metrics
        """
        # Get server configuration from task
        server_file = str(task.get_server_file())
        server_root_dir = str(task.get_server_root_directory())
        mock_config = task.get_mocks()

        # Connect to MCP server with optional mocks
        async with connect_to_mcp_server(
            server_file=server_file,
            server_root_dir=server_root_dir,
            verbose=verbose,
            mock_config=mock_config,
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Get MCP tools
                tools_response = await session.list_tools()
                logger.debug(f'Connected to MCP server with {len(tools_response.tools)} tools')

                # Create context for task
                context = self._create_context(working_directory, bedrock_client)

                # Get prompt from task
                prompt = task.get_prompt(context)

                # Execute prompt (delegated to PromptExecutor)
                logger.debug(f'Running eval for task {task.id}')
                result = await self.prompt_executor.execute_prompt(
                    prompt=prompt,
                    task=task,
                    session=session,
                    tools_response=tools_response,
                    context=context,
                )

                # Add task ID to result
                result['task_id'] = task.id
                return result

    def _create_context(self, working_directory: Path, bedrock_client: Any) -> Dict[str, Any]:
        """Create context dictionary for task execution.

        Args:
            working_directory: Working directory for this task
            bedrock_client: Boto3 Bedrock Runtime client

        Returns:
            Context dictionary passed to tasks, captors, and validators
        """
        return {
            'working_directory': working_directory,
            'bedrock_client': bedrock_client,
        }

    def list_tasks(self) -> List[Dict[str, str]]:
        """List all configured tasks.

        Returns:
            List of task info dictionaries
        """
        return [{'id': task.id, 'type': type(task).__name__} for task in self.tasks]
