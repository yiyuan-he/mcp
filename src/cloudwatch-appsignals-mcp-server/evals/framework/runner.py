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
- Result aggregation and reporting

Heavy lifting delegated to:
- PromptExecutor: Executes individual prompts with agent loop, captors, validators
- ResultAggregator: Aggregates results from multiple prompts
"""

from .aggregator import ResultAggregator
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

    def __init__(self, tasks: List[Task], server_path: str):
        """Initialize evaluation runner.

        Args:
            tasks: List of Task instances to evaluate
            server_path: Path to MCP server.py file (required)

        Raises:
            ValueError: If server_path is not provided
        """
        if not server_path:
            raise ValueError('server_path is required')

        self.tasks = tasks
        self.server_path = server_path

        # Initialize helper classes (Dependency Injection)
        # These could be passed in as parameters for even better testability,
        # but for now we instantiate them here
        self.prompt_executor = PromptExecutor()
        self.result_aggregator = ResultAggregator()

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
        mcp_repo_root: Path,
    ) -> Dict[str, Any]:
        """Run a single task.

        This method orchestrates the high-level flow:
        1. Connect to MCP server
        2. Execute each prompt (delegated to PromptExecutor)
        3. Aggregate results (delegated to ResultAggregator)

        The actual work is delegated to focused helper classes, making this
        method easy to understand and maintain.

        Args:
            task: Task instance
            bedrock_client: Boto3 Bedrock Runtime client
            verbose: Enable verbose logging
            mcp_repo_root: MCP repository root directory

        Returns:
            Result dictionary with validation and metrics
        """
        # Get mock config from task
        mock_config = task.get_mocks()

        # Connect to MCP server with optional mocks
        async with connect_to_mcp_server(
            self.server_path, verbose=verbose, mock_config=mock_config
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Get MCP tools
                tools_response = await session.list_tools()
                logger.debug(f'Connected to MCP server with {len(tools_response.tools)} tools')

                # Create context for task
                context = self._create_context(mcp_repo_root, bedrock_client)

                # Get prompts from task
                prompts = task.get_prompt(context)

                # Execute each prompt (delegated to PromptExecutor)
                prompt_results = []
                for i, prompt in enumerate(prompts):
                    logger.debug(f'Running eval for prompt {i + 1}/{len(prompts)}')

                    result = await self.prompt_executor.execute_prompt(
                        prompt=prompt,
                        prompt_index=i,
                        task=task,
                        session=session,
                        tools_response=tools_response,
                        context=context,
                    )
                    prompt_results.append(result)

                # Aggregate results across all prompts (delegated to ResultAggregator)
                return self.result_aggregator.aggregate_task_results(
                    task_id=task.id, prompt_results=prompt_results
                )

    def _create_context(self, mcp_repo_root: Path, bedrock_client: Any) -> Dict[str, Any]:
        """Create context dictionary for task execution.

        Args:
            mcp_repo_root: MCP repository root directory
            bedrock_client: Boto3 Bedrock Runtime client

        Returns:
            Context dictionary passed to tasks, captors, and validators
        """
        return {
            'mcp_repo_root': mcp_repo_root,
            'bedrock_client': bedrock_client,
        }

    def list_tasks(self) -> List[Dict[str, str]]:
        """List all configured tasks.

        Returns:
            List of task info dictionaries
        """
        return [{'id': task.id, 'type': type(task).__name__} for task in self.tasks]
