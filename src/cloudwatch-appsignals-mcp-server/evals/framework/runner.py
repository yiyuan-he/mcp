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
- Agent loop execution
- Captor execution to extract outputs
- Validator execution to evaluate against rubric
- Results reporting
"""

from loguru import logger
from mcp import ClientSession
from pathlib import Path
from typing import Any, Dict, List

from .agent import run_agent_loop
from .captor import Captor
from .mcp_client import connect_to_mcp_server
from .metrics import MetricsTracker
from .task import Task
from .validator import Validator


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
                result = await self.run_task(
                    task, bedrock_client, verbose, mcp_repo_root
                )
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
                logger.debug(
                    f'Connected to MCP server with {len(tools_response.tools)} tools'
                )

                # Get prompts from task (use enablement-specific method if available)
                if hasattr(task, 'get_prompt_for_project'):
                    prompts = task.get_prompt_for_project(mcp_repo_root)
                else:
                    prompts = task.get_prompt()

                # Run separate eval for each prompt (isolated contexts)
                all_results = []
                for i, prompt in enumerate(prompts):
                    logger.debug(f'Running eval for prompt {i + 1}/{len(prompts)}')

                    # Initialize metrics tracker for this prompt
                    metrics_tracker = MetricsTracker()

                    # Run agent loop with single prompt
                    messages = await run_agent_loop(
                        bedrock_client=bedrock_client,
                        session=session,
                        prompt=prompt,
                        project_root=mcp_repo_root,
                        mcp_tools=tools_response.tools,
                        metrics_tracker=metrics_tracker,
                        max_turns=task.max_turns,
                    )

                    # Execute captors if task defines them
                    captured_data = {'prompt_index': i, 'prompt': prompt}
                    if hasattr(task, 'get_captors'):
                        captors = task.get_captors()
                        for captor in captors:
                            captor_output = captor.capture(
                                messages, metrics_tracker, mcp_repo_root
                            )
                            captured_data.update(captor_output)

                    # Execute validators if task defines them
                    validation_results = []
                    if hasattr(task, 'get_validators_for_project'):
                        validators = task.get_validators_for_project(mcp_repo_root)
                    elif hasattr(task, 'get_validators'):
                        validators = task.get_validators()
                    else:
                        validators = []

                    for validator in validators:
                        validation_result = await validator.validate(
                            captured_data, task.rubric, bedrock_client
                        )
                        validation_results.append(validation_result)

                    # Calculate metrics for this prompt
                    expected_tools = getattr(task, 'expected_tools', [])
                    metrics = metrics_tracker.get_metrics(expected_tools=expected_tools)

                    # Aggregate results for this prompt
                    overall_pass = all(
                        v.get('overall_pass', False) for v in validation_results
                    )

                    all_results.append({
                        'prompt_index': i,
                        'prompt': prompt,
                        'success': overall_pass,
                        'validation_results': validation_results,
                        'metrics': metrics,
                        'captured_data': captured_data,
                    })

                # Aggregate results across all prompts
                overall_task_pass = all(r['success'] for r in all_results)

                return {
                    'task_id': task.id,
                    'success': overall_task_pass,
                    'num_prompts': len(prompts),
                    'prompt_results': all_results,
                }

    def list_tasks(self) -> List[Dict[str, str]]:
        """List all configured tasks.

        Returns:
            List of task info dictionaries
        """
        return [{'id': task.id, 'type': type(task).__name__} for task in self.tasks]
