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

Auto-discovers and runs all tasks defined in *_tasks.py files in the specified directory.

Usage:
    python evals/framework/eval.py applicationsignals                                    # Run all tasks
    python evals/framework/eval.py applicationsignals --list                             # List all available tasks
    python evals/framework/eval.py applicationsignals --task investigation_tasks         # Run all investigation tasks
    python evals/framework/eval.py applicationsignals --task-id petclinic_scheduling_rca # Run specific task
    python evals/framework/eval.py applicationsignals --task investigation_tasks --task-id basic_service_health  # Combine filters
    python evals/framework/eval.py applicationsignals -v                                 # Verbose output
    python evals/framework/eval.py applicationsignals --no-cleanup                       # Skip cleanup after eval
"""

import argparse
import asyncio
import boto3
import importlib
import sys
import traceback
from evals.core import EvalRunner
from evals.core.constants import DEFAULT_AWS_REGION
from loguru import logger
from pathlib import Path
from typing import Any, Dict, List


logger.remove()


def discover_tasks(task_dir: Path) -> tuple[List[Any], Dict[str, List[Any]], Path]:
    """Auto-discover all tasks from *_tasks.py files in the specified directory.

    Args:
        task_dir: Path to directory containing task modules

    Returns:
        Tuple of (all_tasks, tasks_by_module, server_path)
    """
    all_tasks = []
    tasks_by_module = {}
    server_path = None

    # Add evals directory to Python path so framework imports work in task modules
    evals_dir = task_dir.parent
    evals_dir_str = str(evals_dir.absolute())
    if evals_dir_str not in sys.path:
        sys.path.insert(0, evals_dir_str)

    # Add task directory to Python path so we can import task modules
    task_dir_str = str(task_dir.absolute())
    if task_dir_str not in sys.path:
        sys.path.insert(0, task_dir_str)

    # Find all *_tasks.py files in task directory
    task_modules = [f.stem for f in task_dir.glob('*_tasks.py')]

    logger.debug(f'Discovered task modules in {task_dir}: {task_modules}')

    for module_name in task_modules:
        try:
            # Import the module
            module = importlib.import_module(module_name)

            # Get TASKS list if it exists
            if hasattr(module, 'TASKS'):
                tasks = module.TASKS
                all_tasks.extend(tasks)
                tasks_by_module[module_name] = tasks
                logger.debug(f'Loaded {len(tasks)} tasks from {module_name}')

            # Get server path if defined (first one wins)
            if server_path is None and hasattr(module, 'SERVER_PATH'):
                server_path = module.SERVER_PATH
                logger.debug(f'Using server path from {module_name}: {server_path}')

        except Exception as e:
            logger.warning(f'Failed to load tasks from {module_name}: {e}')
            if logger.level('DEBUG').no <= logger._core.min_level:
                traceback.print_exc()

    # Default server path if not specified
    if server_path is None:
        server_path = (
            Path(__file__).parent.parent.parent
            / 'awslabs'
            / 'cloudwatch_appsignals_mcp_server'
            / 'server.py'
        )
        logger.debug(f'Using default server path: {server_path}')

    return all_tasks, tasks_by_module, server_path


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
                logger.info(
                    f'  Validation ({validator_name}): {status} ({passed}/{total} criteria met)'
                )

    # Overall task status
    status = '✅ PASS' if result['success'] else '❌ FAIL'
    logger.info(f'\nOverall Task Status: {status}')
    logger.info('=' * 60 + '\n')


async def main():
    """Entry point for eval script."""
    parser = argparse.ArgumentParser(description='Evaluate MCP tools')
    parser.add_argument(
        'task_dir',
        help='Task directory name (relative to evals/, e.g., "applicationsignals")',
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true', help='Enable verbose/debug logging'
    )
    parser.add_argument(
        '--task',
        help='Run all tasks from specific task file (e.g., investigation_tasks, enablement_tasks)',
    )
    parser.add_argument(
        '--task-id', help='Run specific task by ID (e.g., petclinic_scheduling_rca)'
    )
    parser.add_argument('--list', action='store_true', help='List all available tasks and exit')
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

    # Resolve task directory (relative to evals/, which is parent of framework/)
    evals_dir = Path(__file__).parent.parent
    task_dir = evals_dir / args.task_dir

    if not task_dir.exists():
        logger.error(f'Task directory not found: {task_dir}')
        logger.error(f'Expected to find it at: {task_dir.absolute()}')
        sys.exit(1)

    logger.info(f'Starting MCP tool evaluation for {args.task_dir}\n')

    # Auto-discover tasks
    all_tasks, tasks_by_module, server_path = discover_tasks(task_dir)

    if not all_tasks:
        logger.error('No tasks found in *_tasks.py files')
        sys.exit(1)

    # Handle --list flag
    if args.list:
        logger.info('Available task modules and tasks:\n')
        for module_name, module_tasks in tasks_by_module.items():
            logger.info(f'{module_name}:')
            for task in module_tasks:
                logger.info(f'  - {task.id}')
            logger.info('')
        sys.exit(0)

    # Filter by task module if specified
    if args.task:
        if args.task not in tasks_by_module:
            logger.error(f"Task module '{args.task}' not found")
            logger.info(f'Available modules: {", ".join(tasks_by_module.keys())}')
            sys.exit(1)
        tasks = tasks_by_module[args.task]
    else:
        tasks = all_tasks

    # Filter by task ID if specified
    if args.task_id:
        filtered_tasks = [t for t in tasks if t.id == args.task_id]
        if not filtered_tasks:
            logger.error(f"Task ID '{args.task_id}' not found")
            if args.task:
                logger.info(f'Available tasks in {args.task}: {", ".join(t.id for t in tasks)}')
            else:
                logger.info(f'Available task IDs: {", ".join(t.id for t in all_tasks)}')
            sys.exit(1)
        tasks = filtered_tasks

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

    logger.debug(f'MCP server path: {server_path}')

    # Create runner and execute tasks
    try:
        runner = EvalRunner(tasks=tasks, server_path=str(server_path))

        # Execute each task
        results = []
        for task in tasks:
            # Get working directory from task (or use current directory if not specified)
            working_directory = task.get_working_directory()
            if working_directory is None:
                working_directory = Path.cwd()

            logger.debug(f'Working directory for task {task.id}: {working_directory}')

            result = await runner.run_task(task, bedrock_client, args.verbose, working_directory)
            results.append(result)

        # Report results and cleanup
        for task, result in zip(tasks, results):
            report_task_results(task, result)

            # Call task cleanup
            if not args.no_cleanup:
                working_directory = task.get_working_directory() or Path.cwd()
                context = {'working_directory': working_directory}
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
