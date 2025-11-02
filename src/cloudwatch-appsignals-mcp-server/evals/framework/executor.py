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

"""Prompt execution logic extracted from EvalRunner.

This module implements the Single Responsibility Principle (SRP) by extracting
the prompt execution logic into a focused class.

Before: EvalRunner.run_task() did everything (100+ lines, 8 responsibilities)
After: PromptExecutor handles just prompt execution (single responsibility)

Benefits:
- Easier to test (mock just the agent loop, captors, validators)
- Easier to understand (one clear purpose)
- Easier to modify (change execution logic without touching orchestration)
- Reusable (can use PromptExecutor in other contexts)
"""

from .agent import run_agent_loop
from .metrics import MetricsTracker
from .task import Task
from loguru import logger
from mcp import ClientSession
from pathlib import Path
from typing import Any, Dict


class PromptExecutor:
    """Executes a single prompt and gathers its results.

    Responsibilities:
    1. Run agent loop for the prompt
    2. Execute captors to extract data
    3. Execute validators to check success
    4. Calculate metrics
    5. Aggregate into a prompt result dictionary

    This class follows SRP: it has ONE reason to change - if the way we
    execute and validate a single prompt changes.
    """

    async def execute_prompt(
        self,
        prompt: str,
        prompt_index: int,
        task: Task,
        session: ClientSession,
        tools_response: Any,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a single prompt and gather all results.

        Args:
            prompt: The prompt text to send to the agent
            prompt_index: Index of this prompt in the task's prompt list
            task: The Task instance being evaluated
            session: MCP ClientSession for tool calls
            tools_response: Response from session.list_tools()
            context: Context dictionary with mcp_repo_root, bedrock_client

        Returns:
            Dictionary with prompt execution results:
            {
                'prompt_index': int,
                'prompt': str,
                'success': bool,
                'validation_results': List[Dict],
                'metrics': Dict,
                'captured_data': Dict
            }
        """
        logger.debug(f'Running eval for prompt {prompt_index + 1}')

        # Extract dependencies from context
        bedrock_client = context['bedrock_client']
        mcp_repo_root = context['mcp_repo_root']

        # Step 1: Run agent loop
        metrics_tracker = MetricsTracker()
        messages = await run_agent_loop(
            bedrock_client=bedrock_client,
            session=session,
            prompt=prompt,
            project_root=mcp_repo_root,
            mcp_tools=tools_response.tools,
            metrics_tracker=metrics_tracker,
            max_turns=task.max_turns,
        )

        # Step 2: Execute captors
        captured_data = await self._execute_captors(
            task, context, messages, metrics_tracker, mcp_repo_root, prompt_index, prompt
        )

        # Step 3: Execute validators
        validation_results = await self._execute_validators(
            task, context, captured_data, bedrock_client
        )

        # Step 4: Calculate metrics
        metrics = metrics_tracker.get_metrics(expected_tools=task.expected_tools)

        # Step 5: Aggregate results for this prompt
        overall_pass = all(v.get('overall_pass', False) for v in validation_results)

        return {
            'prompt_index': prompt_index,
            'prompt': prompt,
            'success': overall_pass,
            'validation_results': validation_results,
            'metrics': metrics,
            'captured_data': captured_data,
        }

    async def _execute_captors(
        self,
        task: Task,
        context: Dict[str, Any],
        messages: list,
        metrics_tracker: MetricsTracker,
        mcp_repo_root: Path,
        prompt_index: int,
        prompt: str,
    ) -> Dict[str, Any]:
        """Execute all captors and gather captured data.

        Args:
            task: Task instance
            context: Context dictionary
            messages: Conversation messages from agent loop
            metrics_tracker: Metrics tracker instance
            mcp_repo_root: MCP repository root
            prompt_index: Index of current prompt
            prompt: Prompt text

        Returns:
            Dictionary with captured data from all captors
        """
        captured_data = {'prompt_index': prompt_index, 'prompt': prompt}
        captors = task.get_captors(context)

        for captor in captors:
            captor_output = captor.capture(messages, metrics_tracker, mcp_repo_root)
            captured_data.update(captor_output)

        return captured_data

    async def _execute_validators(
        self,
        task: Task,
        context: Dict[str, Any],
        captured_data: Dict[str, Any],
        bedrock_client: Any,
    ) -> list:
        """Execute all validators and gather validation results.

        Args:
            task: Task instance
            context: Context dictionary
            captured_data: Data captured by captors
            bedrock_client: Bedrock client for LLM validators

        Returns:
            List of validation result dictionaries
        """
        validation_results = []
        validators = task.get_validators(context)

        for validator in validators:
            validation_result = await validator.validate(
                captured_data, task.rubric, bedrock_client
            )
            validation_results.append(validation_result)

        return validation_results
