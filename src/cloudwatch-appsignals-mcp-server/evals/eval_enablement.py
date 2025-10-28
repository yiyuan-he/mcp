"""Enablement Tool Evaluation Script.

Evaluates whether AI assistant can:
1. Call the get_enablement_guide MCP tool
2. Understand the returned instructions
3. Modify project files correctly
4. Pass validation criteria

Usage:
    python eval_enablement.py
"""

import argparse
import asyncio
import boto3
import json
import subprocess
import sys
import time
import traceback
from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pathlib import Path
from typing import Any, Dict, List, Optional


logger.remove()


class MetricsTracker:
    """Tracks metrics for tool calls and task execution."""

    def __init__(self):
        """Initialize metrics tracker."""
        self.tool_calls: List[Dict[str, Any]] = []
        self.task_start_time: Optional[float] = None
        self.task_end_time: Optional[float] = None

    def start_task(self):
        """Mark task start time."""
        self.task_start_time = time.time()

    def end_task(self):
        """Mark task end time."""
        self.task_end_time = time.time()

    def record_tool_call(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        duration: float,
        success: bool,
        error: Optional[str] = None,
    ):
        """Record a tool call."""
        self.tool_calls.append(
            {
                'tool_name': tool_name,
                'parameters': parameters,
                'duration': duration,
                'success': success,
                'error': error,
                'timestamp': time.time(),
            }
        )

    def get_metrics(self, expected_tools: Optional[List[str]] = None) -> Dict[str, Any]:
        """Calculate metrics.

        Args:
            expected_tools: List of MCP tools expected to be used
        """
        metrics = {
            'success_rate': (
                sum(1 for c in self.tool_calls if c['success']) / len(self.tool_calls)
                if self.tool_calls
                else 0.0
            ),
            'tool_call_count': len(self.tool_calls),
            'task_duration': (
                self.task_end_time - self.task_start_time
                if self.task_start_time and self.task_end_time
                else 0.0
            ),
            'tool_calls_detail': self.tool_calls,
        }

        file_ops = ['read_file', 'write_file', 'list_files']
        file_op_calls = [c for c in self.tool_calls if c['tool_name'] in file_ops]

        metrics.update(
            {
                'file_operation_count': len(file_op_calls),
                'file_read_count': len(
                    [c for c in file_op_calls if c['tool_name'] == 'read_file']
                ),
                'file_write_count': len(
                    [c for c in file_op_calls if c['tool_name'] == 'write_file']
                ),
            }
        )

        if expected_tools:
            expected_tool_set = set(expected_tools)
            called_tool_names = {c['tool_name'] for c in self.tool_calls}
            called_expected = called_tool_names & expected_tool_set
            missing = expected_tool_set - called_tool_names
            unexpected = called_tool_names - expected_tool_set

            metrics.update(
                {
                    'hit_rate': len(called_expected) / len(expected_tool_set)
                    if expected_tool_set
                    else 0.0,
                    'expected_tools_called': sorted(called_expected),
                    'missing_expected_tools': sorted(missing),
                    'unexpected_tools_called': sorted(unexpected),
                }
            )

        return metrics


def connect_to_mcp_server(verbose: bool = False):
    """Connect to the MCP server via stdio."""
    import os

    env = os.environ.copy()
    if not verbose:
        env['LOGURU_LEVEL'] = 'ERROR'

    server_params = StdioServerParameters(
        command='python', args=['-m', 'awslabs.cloudwatch_appsignals_mcp_server.server'], env=env
    )

    return stdio_client(server_params)


def convert_mcp_tools_to_bedrock(mcp_tools) -> List[Dict[str, Any]]:
    """Convert MCP tool format to Bedrock tool format."""
    bedrock_tools = []

    for tool in mcp_tools:
        bedrock_tool = {
            'toolSpec': {
                'name': tool.name,
                'description': tool.description or '',
                'inputSchema': {'json': tool.inputSchema},
            }
        }
        bedrock_tools.append(bedrock_tool)

    return bedrock_tools


def get_mock_project_path() -> Path:
    """Get the absolute path to the appsignals-enablement-mock-projects directory.

    This is computed relative to the eval script location, making it portable across machines.
    """
    script_dir = Path(__file__).parent
    return script_dir / '..' / '..' / '..' / 'samples' / 'appsignals-enablement-mock-projects'


def get_file_tools() -> List[Dict[str, Any]]:
    """Define file operation tools."""
    return [
        {
            'toolSpec': {
                'name': 'list_files',
                'description': 'List files in a directory',
                'inputSchema': {
                    'json': {
                        'type': 'object',
                        'properties': {
                            'path': {
                                'type': 'string',
                                'description': 'Path to directory (relative to project root)',
                            }
                        },
                        'required': ['path'],
                    }
                },
            }
        },
        {
            'toolSpec': {
                'name': 'read_file',
                'description': 'Read contents of a file',
                'inputSchema': {
                    'json': {
                        'type': 'object',
                        'properties': {
                            'path': {
                                'type': 'string',
                                'description': 'Path to file (relative to project root)',
                            }
                        },
                        'required': ['path'],
                    }
                },
            }
        },
        {
            'toolSpec': {
                'name': 'write_file',
                'description': 'Write content to a file (overwrites existing content)',
                'inputSchema': {
                    'json': {
                        'type': 'object',
                        'properties': {
                            'path': {
                                'type': 'string',
                                'description': 'Path to file (relative to project root)',
                            },
                            'content': {'type': 'string', 'description': 'Content to write'},
                        },
                        'required': ['path', 'content'],
                    }
                },
            }
        },
    ]


async def execute_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    session: ClientSession,
    project_root: Path,
    metrics_tracker: MetricsTracker,
) -> Dict[str, Any]:
    """Execute a tool call (MCP tool or file operation)."""
    start = time.time()
    success = True
    error = None

    try:
        if tool_name == 'list_files':
            dir_path = project_root / tool_input['path']
            files = [f.name for f in dir_path.iterdir()]
            result = {'content': [{'text': '\n'.join(files)}]}
        elif tool_name == 'read_file':
            file_path = project_root / tool_input['path']
            content = file_path.read_text()
            result = {'content': [{'text': content}]}
        elif tool_name == 'write_file':
            file_path = project_root / tool_input['path']
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(tool_input['content'])
            result = {'content': [{'text': f'Successfully wrote to {tool_input["path"]}'}]}
        else:
            mcp_result = await session.call_tool(tool_name, tool_input)
            result = {'content': [{'text': str(mcp_result.content)}]}

        return result
    except Exception as e:
        logger.error(f'Tool execution failed: {e}')
        success = False
        error = str(e)
        return {'content': [{'text': f'Error: {str(e)}'}], 'status': 'error'}
    finally:
        duration = time.time() - start
        params_to_log = {k: v for k, v in tool_input.items() if k != 'toolUseId'}
        metrics_tracker.record_tool_call(tool_name, params_to_log, duration, success, error)


async def run_agent_loop(
    bedrock_client,
    session: ClientSession,
    task: Dict[str, Any],
    mcp_tools,
    metrics_tracker: MetricsTracker,
) -> List[Dict[str, Any]]:
    """Run the agent loop."""
    metrics_tracker.start_task()

    # Get mock project path (portable across machines)
    project_root = get_mock_project_path()

    # Construct absolute paths for the MCP tool
    # Task config has relative paths, but we pass absolute paths to avoid any ambiguity
    iac_abs_path = project_root / task['iac_directory']
    app_abs_path = project_root / task['app_directory']

    prompt = f"""Enable Application Signals for my {task['language']} {task['framework']} on {task['platform']}.

My infrastructure as code directory is: {iac_abs_path}
My application directory is: {app_abs_path}"""

    logger.debug('Sending prompt to Claude...')

    bedrock_mcp_tools = convert_mcp_tools_to_bedrock(mcp_tools)
    file_tools = get_file_tools()
    all_tools = bedrock_mcp_tools + file_tools

    toolConfig = {'tools': all_tools}
    logger.debug(f'Configured {len(all_tools)} tools')

    messages = [{'role': 'user', 'content': [{'text': prompt}]}]

    max_turns = 20
    turn = 0

    while turn < max_turns:
        turn += 1
        logger.debug(f'=== Turn {turn}/{max_turns} ===')

        start = time.time()

        try:
            response = bedrock_client.converse(
                modelId='us.anthropic.claude-sonnet-4-20250514-v1:0',
                messages=messages,
                toolConfig=toolConfig,
                inferenceConfig={'temperature': 0.0},
            )

            elapsed = time.time() - start
            logger.debug(f'Claude responded in {elapsed:.2f}s')
            logger.debug(f'Stop reason: {response["stopReason"]}')

            messages.append(
                {'role': 'assistant', 'content': response['output']['message']['content']}
            )

            if response['stopReason'] == 'end_turn':
                logger.debug('Claude finished!')
                break
            elif response['stopReason'] == 'tool_use':
                tool_results = []

                for content_block in response['output']['message']['content']:
                    if 'toolUse' in content_block:
                        tool_use = content_block['toolUse']
                        tool_name = tool_use['name']
                        tool_input = tool_use['input']
                        tool_use_id = tool_use['toolUseId']

                        logger.debug(f'Tool requested: {tool_name}')

                        tool_input['toolUseId'] = tool_use_id
                        result = await execute_tool(
                            tool_name, tool_input, session, project_root, metrics_tracker
                        )

                        tool_results.append(
                            {
                                'toolResult': {
                                    'toolUseId': tool_use_id,
                                    'content': result['content'],
                                }
                            }
                        )

                messages.append({'role': 'user', 'content': tool_results})
            else:
                logger.warning(f'Unexpected stop reason: {response["stopReason"]}')
                break
        except Exception as e:
            logger.error(f'Error in agent loop: {e}')
            raise

    if turn >= max_turns:
        logger.warning(f'Reached max turns ({max_turns})')

    metrics_tracker.end_task()

    return messages


async def validate_with_llm(
    bedrock_client, task: Dict[str, Any], project_root: Path
) -> Dict[str, Any]:
    """Use LLM to validate changes against rubric."""
    logger.info('Running LLM-as-judge validation...')

    # Try to build the IaC to verify it compiles
    build_result = None
    iac_path = project_root / task['iac_directory']

    # Handle _package.json rename (used to avoid CI detection)
    package_json_path = iac_path / 'package.json'
    underscore_package_path = iac_path / '_package.json'
    renamed_package = False

    if underscore_package_path.exists() and not package_json_path.exists():
        logger.info('Renaming _package.json to package.json for build...')
        underscore_package_path.rename(package_json_path)
        renamed_package = True

    if package_json_path.exists():
        # Install dependencies if node_modules doesn't exist
        if not (iac_path / 'node_modules').exists():
            logger.info('Installing npm dependencies...')
            try:
                install_cmd = subprocess.run(
                    ['npm', 'install'], cwd=iac_path, capture_output=True, text=True, timeout=120
                )
                if install_cmd.returncode != 0:
                    logger.error(f'npm install failed: {install_cmd.stderr}')
            except Exception as e:
                logger.error(f'Failed to install dependencies: {e}')

        logger.info('Running npm run build to validate IaC changes...')
        try:
            build_cmd = subprocess.run(
                ['npm', 'run', 'build'], cwd=iac_path, capture_output=True, text=True, timeout=60
            )
            build_result = {
                'exit_code': build_cmd.returncode,
                'stdout': build_cmd.stdout,
                'stderr': build_cmd.stderr,
                'success': build_cmd.returncode == 0,
            }
            if build_result['success']:
                logger.info('✓ Build succeeded')
            else:
                logger.error(f'✗ Build failed with exit code {build_cmd.returncode}')
        except Exception as e:
            logger.error(f'Build validation error: {e}')
            build_result = {'exit_code': -1, 'stdout': '', 'stderr': str(e), 'success': False}
        finally:
            # Rename back to _package.json if we renamed it earlier
            if renamed_package and package_json_path.exists():
                logger.info('Renaming package.json back to _package.json...')
                package_json_path.rename(underscore_package_path)

    try:
        result = subprocess.run(
            ['git', 'diff'], cwd=project_root, capture_output=True, text=True, timeout=10
        )
        git_diff = result.stdout

        if not git_diff.strip():
            logger.warning('No git diff found - no changes were made')
            return {
                'overall_pass': False,
                'error': 'No changes detected',
                'criteria_results': [],
                'git_diff': '',
            }
    except Exception as e:
        logger.error(f'Failed to get git diff: {e}')
        return {
            'overall_pass': False,
            'error': f'Git diff error: {str(e)}',
            'criteria_results': [],
            'git_diff': '',
        }

    rubric_items = '\n'.join(
        [f'{i + 1}. {criterion}' for i, criterion in enumerate(task['validation_rubric'])]
    )

    # Format build result
    build_info = ''
    if build_result:
        if build_result['success']:
            build_info = '\n**Build Validation:**\n✓ TypeScript compilation succeeded (npm run build exited with code 0)\n'
        else:
            build_info = f'\n**Build Validation:**\n✗ TypeScript compilation FAILED (exit code {build_result["exit_code"]})\n\nBuild errors:\n{build_result["stderr"][:500]}\n'

    prompt = f"""You are evaluating code changes for enabling AWS Application Signals.

**Validation Rubric:**
{rubric_items}
{build_info}
**Git Diff of Changes:**
```diff
{git_diff}
```

Instructions:
For each criterion in the rubric, evaluate whether it is satisfied by the changes and build result.

Respond in this EXACT format:
1. [PASS/FAIL] Brief reasoning (1 sentence)
2. [PASS/FAIL] Brief reasoning (1 sentence)
... (continue for all {len(task['validation_rubric'])} criteria)

Be strict but fair. Only mark as PASS if the criterion is clearly met."""

    try:
        start = time.time()

        response = bedrock_client.converse(
            modelId='us.anthropic.claude-sonnet-4-20250514-v1:0',
            messages=[{'role': 'user', 'content': [{'text': prompt}]}],
            inferenceConfig={'temperature': 0.0},
        )

        elapsed = time.time() - start
        logger.debug(f'LLM validation took {elapsed:.2f}s')

        response_text = response['output']['message']['content'][0]['text']
        logger.debug(f'LLM response:\n{response_text}')

        criteria_results = []
        for line in response_text.strip().split('\n'):
            if not line.strip():
                continue

            if '[PASS]' in line.upper():
                status = 'PASS'
                reasoning = line.split('[PASS]', 1)[1].strip() if '[PASS]' in line else line
            elif '[FAIL]' in line.upper():
                status = 'FAIL'
                reasoning = line.split('[FAIL]', 1)[1].strip() if '[FAIL]' in line else line
            else:
                continue

            if len(criteria_results) < len(task['validation_rubric']):
                criteria_results.append(
                    {
                        'criterion': task['validation_rubric'][len(criteria_results)],
                        'status': status,
                        'reasoning': reasoning,
                    }
                )

        overall_pass = all(r['status'] == 'PASS' for r in criteria_results)

        return {
            'overall_pass': overall_pass,
            'criteria_results': criteria_results,
            'raw_response': response_text,
            'git_diff': git_diff,
        }
    except Exception as e:
        logger.error(f'LLM validation failed: {e}')
        return {
            'overall_pass': False,
            'error': f'Validation error: {str(e)}',
            'criteria_results': [],
            'git_diff': git_diff,
        }


def cleanup_git_state(task):
    """Reset git state after evaluation.

    Only cleans the directories specified in the task (iac_directory, app_directory)
    to avoid clearing unrelated changes in the repo.
    """
    project_root = get_mock_project_path()

    paths_to_clean = []

    if task.get('iac_directory'):
        paths_to_clean.append(task['iac_directory'])

    if task.get('app_directory'):
        paths_to_clean.append(task['app_directory'])

    if not paths_to_clean:
        logger.warning('No directories specified to clean')
        return

    try:
        for path in paths_to_clean:
            logger.debug(f'Cleaning path: {path}')

            subprocess.run(
                ['git', 'checkout', 'HEAD', '--', path],
                cwd=project_root,
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ['git', 'clean', '-fd', path], cwd=project_root, capture_output=True, timeout=10
            )

        logger.debug(f'Reset git state for:  {", ".join(paths_to_clean)}')
    except Exception as e:
        logger.warning(f'Failed to reset git state: {e}')


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

    try:
        bedrock_client = boto3.client(service_name='bedrock-runtime', region_name='us-east-1')
        logger.debug('Bedrock client initialized')
    except Exception as e:
        logger.error(f'Failed to initialize Bedrock client: {e}')
        logger.error('Make sure AWS credentials are configured')
        sys.exit(1)

    tasks_file = Path(__file__).parent / 'tasks' / 'enablement_tasks.json'
    with open(tasks_file) as f:
        all_tasks = json.load(f)

    if args.task:
        all_tasks = [t for t in all_tasks if t['id'] == args.task]
        if not all_tasks:
            logger.error(f"Task '{args.task}' not found")
            sys.exit(1)

    logger.info(f'Loaded {len(all_tasks)} task(s)')
    for task in all_tasks:
        logger.info(f'  - {task["id"]}: {task["platform"]} + {task["language"]}')
    logger.info('')

    logger.debug('Connecting to MCP server...')

    async with connect_to_mcp_server(args.verbose) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_response = await session.list_tools()
            logger.debug(f'Connected to MCP server with {len(tools_response.tools)} tools')

            for task in all_tasks:
                logger.info(f'Running: {task["id"]}...')

                metrics_tracker = MetricsTracker()

                try:
                    _messages = await run_agent_loop(
                        bedrock_client, session, task, tools_response.tools, metrics_tracker
                    )

                    expected_tools = task.get('expected_tools', ['get_enablement_guide'])
                    metrics = metrics_tracker.get_metrics(expected_tools=expected_tools)

                    project_root = get_mock_project_path()
                    validation = await validate_with_llm(bedrock_client, task, project_root)

                    logger.info('\n' + '=' * 60)
                    logger.info(f'EVALUATION COMPLETE: {task["id"]}')
                    logger.info('=' * 60)
                    logger.info(f'Duration: {metrics["task_duration"]:.2f}s')
                    logger.info(f'Hit Rate: {metrics.get("hit_rate", 0):.1%}')
                    logger.info(f'Success Rate: {metrics["success_rate"]:.1%}')
                    logger.info(f'File Operations: {metrics["file_operation_count"]}')

                    if validation.get('error'):
                        logger.info('Validation: ❌ ERROR')
                    else:
                        passed = sum(
                            1 for r in validation['criteria_results'] if r['status'] == 'PASS'
                        )
                        total = len(validation['criteria_results'])
                        status = '✅ PASS' if validation['overall_pass'] else '❌ FAIL'
                        logger.info(f'Validation: {status} ({passed}/{total} criteria met)')

                    logger.info('=' * 60 + '\n')
                except Exception as e:
                    logger.error(f'Evaluation failed: {e}')
                    if args.verbose:
                        traceback.print_exc()
                finally:
                    if not args.no_cleanup:
                        cleanup_git_state(task)
                    else:
                        logger.info('Skipping git cleanup (--no-cleanup flag set)')

            await asyncio.sleep(1)


if __name__ == '__main__':
    asyncio.run(main())
