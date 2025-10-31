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

"""Enablement Tool Evaluation Script.

Evaluates whether AI assistant can:
1. Call the get_enablement_guide MCP tool
2. Understand the returned instructions
3. Modify project files correctly
4. Pass validation criteria

Usage:
    python evals/eval_enablement.py
    python evals/eval_enablement.py -v
    python evals/eval_enablement.py --task ec2_python_flask
    python evals/eval_enablement.py --no-cleanup
"""

import argparse
import asyncio
import boto3
import json
import subprocess
import sys
import traceback
from framework import EvalRunner
from framework.constants import DEFAULT_AWS_REGION
from loguru import logger
from pathlib import Path
from tasks.enablement import EnablementTask
from typing import Any, Dict


logger.remove()


def cleanup_enablement_changes(mcp_repo_root: Path, task: EnablementTask):
    """Clean up git changes made by enablement agent.

    Enablement-specific cleanup that resets paths specified in task.

    Args:
        mcp_repo_root: Absolute path to MCP repository root
        task: EnablementTask with git_paths (relative to mcp_repo_root)
    """
    if not task.git_paths:
        logger.warning('No git_paths specified to clean')
        return

    try:
        for rel_path in task.git_paths:
            full_path = str(mcp_repo_root / rel_path)
            logger.debug(f'Cleaning path: {full_path}')
            subprocess.run(
                ['git', 'checkout', 'HEAD', '--', full_path],
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ['git', 'clean', '-fd', full_path],
                capture_output=True,
                timeout=10,
            )
        logger.debug(f'Reset git state for: {", ".join(task.git_paths)}')
    except Exception as e:
        logger.warning(f'Failed to reset git state: {e}')


def get_mock_project_path() -> Path:
    """Get the absolute path to the get-enablement-guide-samples directory.

    This is computed relative to the eval script location, making it portable across machines.
    """
    script_dir = Path(__file__).parent
    return (
        script_dir
        / '..'
        / '..'
        / '..'
        / 'samples'
        / 'cloudwatch-appsignals-mcp-server'
        / 'get-enablement-guide-samples'
    )


def report_task_results(task: EnablementTask, result: Dict[str, Any]) -> None:
    """Report results for a single task.

    Args:
        task: EnablementTask instance
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

    # Report results for each prompt (usually just one for enablement)
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
    parser = argparse.ArgumentParser(description='Evaluate Application Signals enablement tool')
    parser.add_argument(
        '--verbose', '-v', action='store_true', help='Enable verbose/debug logging'
    )
    parser.add_argument('--task', help='Run specific task by ID (default: run all)')
    parser.add_argument(
        '--no-cleanup',
        action='store_true',
        help='Skip git cleanup after evaluation (useful for inspecting changes)',
    )

    args = parser.parse_args()

    if args.verbose:
        logger.add(sys.stderr, level='DEBUG', format='<level>{message}</level>')
    else:
        logger.add(sys.stderr, level='INFO', format='<level>{message}</level>')

    logger.info('Starting Application Signals enablement evaluation\n')

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

    # Load tasks from JSON
    tasks_file = Path(__file__).parent / 'tasks' / 'enablement_tasks.json'
    with open(tasks_file) as f:
        task_dicts = json.load(f)

    # Filter by task ID if specified
    if args.task:
        task_dicts = [t for t in task_dicts if t['id'] == args.task]
        if not task_dicts:
            logger.error(f"Task '{args.task}' not found")
            sys.exit(1)

    # Convert to EnablementTask instances
    tasks = [EnablementTask.from_dict(t) for t in task_dicts]

    logger.info(f'Loaded {len(tasks)} task(s)')
    for task in tasks:
        logger.info(f'  - {task.id}: {task.platform} + {task.language}')
    logger.info('')

    # Get server path (relative to evals/eval_enablement.py)
    # evals/eval_enablement.py -> evals/ -> cloudwatch-appsignals-mcp-server/ -> awslabs/...
    server_path = Path(__file__).parent.parent / 'awslabs' / 'cloudwatch_appsignals_mcp_server' / 'server.py'
    logger.debug(f'MCP server path: {server_path}')

    # Get MCP repository root (where samples/ directory is)
    mcp_repo_root = Path(__file__).parent.parent.parent.parent
    if not (mcp_repo_root / 'samples').exists():
        logger.error(f'Could not find samples/ directory at {mcp_repo_root}')
        sys.exit(1)

    logger.debug(f'MCP repository root: {mcp_repo_root}')

    # Create runner and execute tasks
    try:
        runner = EvalRunner(tasks=tasks, server_path=str(server_path))

        # Execute each task with mcp_repo_root
        results = []
        for task in tasks:
            result = await runner.run_task(
                task, bedrock_client, args.verbose, mcp_repo_root
            )
            results.append(result)

        # Report results and cleanup
        for task, result in zip(tasks, results):
            report_task_results(task, result)

            # Clean up git changes if task modifies code
            if task.modifies_code:
                if not args.no_cleanup:
                    cleanup_enablement_changes(mcp_repo_root, task)
                else:
                    logger.info(f'Skipping git cleanup for {task.id} (--no-cleanup flag set)')

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
