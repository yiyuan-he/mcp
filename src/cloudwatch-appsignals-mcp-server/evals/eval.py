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

"""Generic evaluation script for MCP tools.

Auto-discovers and runs all tasks defined in tasks/ directory.

Usage:
    python evals/eval.py
    python evals/eval.py -v
    python evals/eval.py --task ec2_python_flask
    python evals/eval.py --no-cleanup
"""

import argparse
import asyncio
import boto3
import importlib
import sys
import traceback
from framework import EvalRunner
from framework.constants import DEFAULT_AWS_REGION
from loguru import logger
from pathlib import Path
from typing import Any, Dict, List

logger.remove()


def discover_tasks() -> tuple[List[Any], Path]:
    """Auto-discover all tasks from *_tasks.py files in evals/ directory.

    Returns:
        Tuple of (all_tasks, server_path)
    """
    evals_dir = Path(__file__).parent
    all_tasks = []
    server_path = None

    # Find all *_tasks.py files in evals/ directory
    task_modules = [
        f.stem for f in evals_dir.glob('*_tasks.py')
    ]

    logger.debug(f'Discovered task modules: {task_modules}')

    for module_name in task_modules:
        try:
            # Import the module
            module = importlib.import_module(module_name)

            # Get TASKS list if it exists
            if hasattr(module, 'TASKS'):
                tasks = module.TASKS
                all_tasks.extend(tasks)
                logger.debug(f'Loaded {len(tasks)} tasks from {module_name}')

            # Get server path if defined (first one wins)
            if server_path is None and hasattr(module, 'SERVER_PATH'):
                server_path = module.SERVER_PATH
                logger.debug(f'Using server path from {module_name}: {server_path}')

        except Exception as e:
            logger.warning(f'Failed to load tasks from {module_name}: {e}')

    # Default server path if not specified
    if server_path is None:
        server_path = Path(__file__).parent.parent / 'awslabs' / 'cloudwatch_appsignals_mcp_server' / 'server.py'
        logger.debug(f'Using default server path: {server_path}')

    return all_tasks, server_path


def report_task_results(task: Any, result: Dict[str, Any]) -> None:
    """Report results for a single task.

    Args:
        task: Task instance
        result: Result dictionary from EvalRunner
    """
    logger.info('\n' + '=' * 60)
    logger.info(f'EVALUATION COMPLETE: {task.id}')
    logger.info('=' * 60)

    if result.get('error'):
        logger.info('Status: ❌ ERROR')
        logger.error(result['error'])
        logger.info('=' * 60 + '\n')
        return

    # Report results for each prompt
    for prompt_result in result['prompt_results']:
        prompt_idx = prompt_result['prompt_index']
        metrics = prompt_result['metrics']

        logger.info(f'Prompt {prompt_idx + 1}/{result["num_prompts"]}:')
        logger.info(f'  Duration: {metrics["task_duration"]:.2f}s')
        logger.info(f'  Hit Rate: {metrics.get("hit_rate", 0):.1%}')
        logger.info(f'  Success Rate: {metrics["success_rate"]:.1%}')
        logger.info(f'  File Operations: {metrics["file_operation_count"]}')

        # Report validation results
        for validation_result in prompt_result['validation_results']:
            validator_name = validation_result.get('validator_name', 'Unknown')
            if validation_result.get('error'):
                logger.info(f'  Validation ({validator_name}): ❌ ERROR')
                logger.error(f'  {validation_result["error"]}')
            else:
                criteria_results = validation_result.get('criteria_results', [])
                passed = sum(1 for r in criteria_results if r['status'] == 'PASS')
                total = len(criteria_results)
                status = '✅ PASS' if validation_result['overall_pass'] else '❌ FAIL'
                logger.info(f'  Validation ({validator_name}): {status} ({passed}/{total} criteria met)')

    # Overall task status
    status = '✅ PASS' if result['success'] else '❌ FAIL'
    logger.info(f'\nOverall Task Status: {status}')
    logger.info('=' * 60 + '\n')


async def main():
    """Entry point for eval script."""
    parser = argparse.ArgumentParser(description='Evaluate MCP tools')
    parser.add_argument(
        '--verbose', '-v', action='store_true', help='Enable verbose/debug logging'
    )
    parser.add_argument('--task', help='Run specific task by ID (default: run all)')
    parser.add_argument(
        '--no-cleanup',
        action='store_true',
        help='Skip cleanup after evaluation (useful for inspecting changes)',
    )

    args = parser.parse_args()

    if args.verbose:
        logger.add(sys.stderr, level='DEBUG', format='<level>{message}</level>')
    else:
        logger.add(sys.stderr, level='INFO', format='<level>{message}</level>')

    logger.info('Starting MCP tool evaluation\n')

    # Auto-discover tasks
    all_tasks, server_path = discover_tasks()

    if not all_tasks:
        logger.error('No tasks found in tasks/ directory')
        sys.exit(1)

    # Filter by task ID if specified
    if args.task:
        tasks = [t for t in all_tasks if t.id == args.task]
        if not tasks:
            logger.error(f"Task '{args.task}' not found")
            logger.info(f"Available tasks: {', '.join(t.id for t in all_tasks)}")
            sys.exit(1)
    else:
        tasks = all_tasks

    logger.info(f'Loaded {len(tasks)} task(s)')
    for task in tasks:
        logger.info(f'  - {task.id}')
    logger.info('')

    # Initialize Bedrock client
    try:
        bedrock_client = boto3.client(
            service_name='bedrock-runtime', region_name=DEFAULT_AWS_REGION
        )
        logger.debug('Bedrock client initialized')
    except Exception as e:
        logger.error(f'Failed to initialize Bedrock client: {e}')
        logger.error('Make sure AWS credentials are configured')
        sys.exit(1)

    # Get MCP repository root (where samples/ directory is)
    mcp_repo_root = Path(__file__).parent.parent.parent.parent
    if not (mcp_repo_root / 'samples').exists():
        logger.error(f'Could not find samples/ directory at {mcp_repo_root}')
        sys.exit(1)

    logger.debug(f'MCP repository root: {mcp_repo_root}')
    logger.debug(f'MCP server path: {server_path}')

    # Create runner and execute tasks
    try:
        runner = EvalRunner(tasks=tasks, server_path=str(server_path))

        # Execute each task
        results = []
        for task in tasks:
            result = await runner.run_task(
                task, bedrock_client, args.verbose, mcp_repo_root
            )
            results.append(result)

        # Report results and cleanup
        for task, result in zip(tasks, results):
            report_task_results(task, result)

            # Call task cleanup
            if not args.no_cleanup:
                context = {'mcp_repo_root': mcp_repo_root}
                task.cleanup(context)

        # Give subprocess time to clean up before event loop closes (Python < 3.11)
        # MCP SDK's stdio_client relies on __del__ for subprocess cleanup
        await asyncio.sleep(0.1)

    except Exception as e:
        logger.error(f'Evaluation failed: {e}')
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('\nInterrupted by user')
        sys.exit(0)
