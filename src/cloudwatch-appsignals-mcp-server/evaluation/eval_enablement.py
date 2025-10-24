import argparse
import asyncio
import json
import sys
from pathlib import Path

import boto3
from loguru import logger

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Logger will be configured after parsing command line args
logger.remove()


class MetricsTracker:
    """Tracks evaluation metrics for tool usage and task completion."""

    def __init__(self):
        self.tool_calls = []
        self.task_start_time = None
        self.task_end_time = None

    def start_task(self):
        """Mark task start time."""
        import time
        self.task_start_time = time.time()

    def end_task(self):
        """Mark task end time."""
        import time
        self.task_end_time = time.time()

    def record_tool_call(self, tool_name, parameters, duration, success, error=None):
        """Record a tool call with timing and success information."""
        import time
        self.tool_calls.append({
            "tool_name": tool_name,
            "parameters": parameters,
            "duration": duration,
            "success": success,
            "error": error,
            "timestamp": time.time()
        })

    def get_metrics(self):
        """Calculate and return all metrics."""
        enablement_calls = [c for c in self.tool_calls
                           if c["tool_name"] == "enable_application_signals"]
        file_op_calls = [c for c in self.tool_calls
                        if c["tool_name"] in ["read_file", "write_file", "list_files"]]

        return {
            "hit_rate": 1.0 if enablement_calls else 0.0,
            "success_rate": (
                sum(1 for c in self.tool_calls if c["success"]) / len(self.tool_calls)
                if self.tool_calls else 0.0
            ),
            "unnecessary_tool_calls": max(0, len(enablement_calls) - 1),
            "file_operation_count": len(file_op_calls),
            "task_duration": (
                self.task_end_time - self.task_start_time
                if self.task_start_time and self.task_end_time else 0.0
            ),
            "total_tool_calls": len(self.tool_calls),
            "tool_calls_detail": self.tool_calls
        }


def generate_report(task, metrics, validation_results, project_root):
    """Generate detailed markdown evaluation report."""
    from datetime import datetime
    import subprocess

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Get git diff
    try:
        result = subprocess.run(
            ["git", "diff"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        git_diff = result.stdout if result.stdout.strip() else "No changes detected"
    except Exception:
        git_diff = "Could not retrieve git diff"

    # Build report
    lines = [
        "# Application Signals Enablement Evaluation Report",
        f"\n**Generated:** {timestamp}",
        f"**Task:** {task['id']}",
        f"**Platform:** {task['platform']}",
        f"**Language:** {task['language']}",
        "\n---\n",
        "## Summary\n",
        f"- **Overall Result:** {'✅ PASS' if validation_results['overall_pass'] else '❌ FAIL'}",
        f"- **Duration:** {metrics['task_duration']:.2f}s",
        f"- **Turns:** {len([c for c in metrics['tool_calls_detail'] if c['tool_name'] != 'enable_application_signals']) // 2 + 1}",
        "\n---\n",
        "## Metrics\n",
        f"- **Hit Rate:** {metrics['hit_rate']:.1%}",
        f"- **Success Rate:** {metrics['success_rate']:.1%}",
        f"- **Unnecessary Tool Calls:** {metrics['unnecessary_tool_calls']}",
        f"- **File Operations:** {metrics['file_operation_count']}",
        f"- **Total Tool Calls:** {metrics['total_tool_calls']}",
        "\n---\n",
        "## Tool Call Trace\n"
    ]

    # Add tool calls
    for i, call in enumerate(metrics['tool_calls_detail'], 1):
        status = "✅" if call['success'] else "❌"
        lines.append(f"{i}. {status} `{call['tool_name']}` ({call['duration']:.2f}s)")

        # Add parameters (excluding toolUseId)
        if call['parameters']:
            for key, value in call['parameters'].items():
                # Truncate long values
                value_str = str(value)
                if len(value_str) > 100:
                    value_str = value_str[:100] + "..."
                lines.append(f"   - {key}: {value_str}")

        if call.get('error'):
            lines.append(f"   - ❌ Error: {call['error']}")
        lines.append("")

    # Add validation results
    lines.extend([
        "\n---\n",
        "## Validation Results\n",
        "### LLM-as-Judge Assessment\n"
    ])

    if validation_results.get("error"):
        lines.append(f"❌ **Error:** {validation_results['error']}\n")
    else:
        for result in validation_results["criteria_results"]:
            status = "✅ PASS" if result["status"] == "PASS" else "❌ FAIL"
            lines.append(f"\n**{status}:** {result['criterion']}")
            lines.append(f"\n_{result['reasoning']}_\n")

    # Add git diff
    lines.extend([
        "\n---\n",
        "## Git Diff\n",
        "```diff",
        git_diff,
        "```"
    ])

    return "\n".join(lines)


async def validate_with_llm(bedrock_client, task, project_root):
    """Use LLM as judge to validate code changes against rubric."""
    import subprocess

    logger.info("Running LLM-as-judge validation...")

    # Get git diff
    try:
        result = subprocess.run(
            ["git", "diff"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        git_diff = result.stdout

        if not git_diff.strip():
            logger.warning("No git diff found - no changes were made")
            return {
                "overall_pass": False,
                "error": "No changes detected in git diff",
                "criteria_results": []
            }
    except Exception as e:
        logger.error(f"Failed to get git diff: {e}")
        return {
            "overall_pass": False,
            "error": f"Failed to get git diff: {str(e)}",
            "criteria_results": []
        }

    # Build validation prompt
    rubric_items = "\n".join([f"{i+1}. {criterion}" for i, criterion in enumerate(task["validation_rubric"])])

    prompt = f"""You are evaluating code changes for enabling AWS Application Signals on an application.

**Validation Rubric:**
{rubric_items}

**Git Diff of Changes:**
```diff
{git_diff}
```

**Instructions:**
For each criterion in the rubric, evaluate whether it is satisfied by the changes shown in the git diff.

Respond in this EXACT format:
1. [PASS/FAIL] Brief reasoning (1 sentence)
2. [PASS/FAIL] Brief reasoning (1 sentence)
... (continue for all {len(task["validation_rubric"])} criteria)

Be strict but fair. Only mark as PASS if the criterion is clearly met."""

    # Call Bedrock
    try:
        import time
        start = time.time()

        response = bedrock_client.converse(
            modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            inferenceConfig={
                "temperature": 0.0
            }
        )

        elapsed = time.time() - start
        logger.debug(f"LLM validation took {elapsed:.2f}s")

        # Extract response text
        response_text = ""
        for content in response['output']['message']['content']:
            if 'text' in content:
                response_text = content['text']
                break

        logger.debug(f"LLM validation response:\n{response_text}")

        # Parse response
        criteria_results = []
        lines = response_text.strip().split('\n')

        for i, line in enumerate(lines):
            if line.strip():
                # Extract PASS/FAIL
                if '[PASS]' in line.upper():
                    status = 'PASS'
                    reasoning = line.split('[PASS]', 1)[1].strip() if '[PASS]' in line else line
                elif '[FAIL]' in line.upper():
                    status = 'FAIL'
                    reasoning = line.split('[FAIL]', 1)[1].strip() if '[FAIL]' in line else line
                else:
                    continue

                criteria_results.append({
                    "criterion": task["validation_rubric"][len(criteria_results)] if len(criteria_results) < len(task["validation_rubric"]) else "Unknown",
                    "status": status,
                    "reasoning": reasoning
                })

        overall_pass = all(r["status"] == "PASS" for r in criteria_results)

        return {
            "overall_pass": overall_pass,
            "criteria_results": criteria_results,
            "raw_response": response_text
        }

    except Exception as e:
        logger.error(f"LLM validation failed: {e}")
        return {
            "overall_pass": False,
            "error": f"LLM validation error: {str(e)}",
            "criteria_results": []
        }


def connect_to_mcp_server(verbose=False):
    """Connect to MCP server, optionally suppressing its logs."""
    import os

    env = os.environ.copy()
    if not verbose:
        # Suppress MCP server logs in non-verbose mode
        env["LOGURU_LEVEL"] = "ERROR"

    server_params = StdioServerParameters(
        command="python",
        args=["-m", "awslabs.cloudwatch_appsignals_mcp_server.server"],
        env=env
    )

    return stdio_client(server_params)


def convert_mcp_tools_to_bedrock(mcp_tools):
    """Convert MCP tool format to Bedrock tool format."""
    bedrock_tools = []

    for tool in mcp_tools:
        bedrock_tool = {
            "toolSpec": {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": {
                    "json": tool.inputSchema
                }
            }
        }
        bedrock_tools.append(bedrock_tool)

    return bedrock_tools


def get_file_tools():
    """Define file operation tools for Claude to use."""
    return [
        {
            "toolSpec": {
                "name": "list_files",
                "description": "List files in a directory",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the directory to list"
                            }
                        },
                        "required": ["path"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "read_file",
                "description": "Read contents of a file",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the file to read"
                            }
                        },
                        "required": ["path"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "write_file",
                "description": "Write content to a file (overwrites existing content)",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the file to write"
                            },
                            "content": {
                                "type": "string",
                                "description": "Content to write to the file"
                            }
                        },
                        "required": ["path", "content"]
                    }
                }
            }
        }
    ]


async def execute_tool(tool_name, tool_input, session, project_root, metrics_tracker):
    """Execute a tool call - either MCP tool or file operation."""
    logger.debug(f"Executing tool: {tool_name}")

    import time
    start = time.time()
    success = True
    error = None

    try:
        # File operation tools - handle locally
        if tool_name == "list_files":
            dir_path = Path(project_root) / tool_input["path"]
            files = [f.name for f in dir_path.iterdir()]
            files_list = "\n".join(files)
            return {
                "toolUseId": tool_input.get("toolUseId", ""),
                "content": [{"text": files_list}]
            }

        elif tool_name == "read_file":
            file_path = Path(project_root) / tool_input["path"]
            content = file_path.read_text()
            return {
                "toolUseId": tool_input.get("toolUseId", ""),
                "content": [{"text": content}]
            }

        elif tool_name == "write_file":
            file_path = Path(project_root) / tool_input["path"]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(tool_input["content"])
            return {
                "toolUseId": tool_input.get("toolUseId", ""),
                "content": [{"text": f"Successfully wrote to {tool_input['path']}"}]
            }

        # MCP tools - route through session
        else:
            result = await session.call_tool(tool_name, tool_input)
            return {
                "toolUseId": tool_input.get("toolUseId", ""),
                "content": [{"text": str(result.content)}]
            }

    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}")
        success = False
        error = str(e)
        return {
            "toolUseId": tool_input.get("toolUseId", ""),
            "content": [{"text": f"Error: {str(e)}"}],
            "status": "error"
        }
    finally:
        # Record metrics for this tool call
        duration = time.time() - start
        # Remove toolUseId from parameters for cleaner logging
        params_to_log = {k: v for k, v in tool_input.items() if k != "toolUseId"}
        metrics_tracker.record_tool_call(tool_name, params_to_log, duration, success, error)


async def run_agent_loop(bedrock_client, session, task, mcp_tools):
    """Run the agent loop: send prompts to Claude, handle tool calls, repeat."""

    # Initialize metrics tracker
    metrics_tracker = MetricsTracker()
    metrics_tracker.start_task()

    prompt = f"""Enable Application Signals for my {task['language']} {task['framework']} application on {task['platform']}.

My infrastructure as code directory is: {task['iac_directory']}
My application directory is: {task['app_directory']}

Please use the enable_application_signals tool to get enablement instructions, then modify the necessary files to enable Application Signals."""

    logger.debug(f"Sending initial prompt to Claude...")

    # Build tool config
    bedrock_mcp_tools = convert_mcp_tools_to_bedrock(mcp_tools)
    file_tools = get_file_tools()
    all_tools = bedrock_mcp_tools + file_tools

    toolConfig = {"tools": all_tools}
    logger.debug(f"Configured {len(all_tools)} tools for Claude")

    # Start conversation
    messages = [
        {
            "role": "user",
            "content": [{"text": prompt}]
        }
    ]

    project_root = task["mock_project_path"]
    max_turns = 20  # Prevent infinite loops
    turn = 0

    import time

    while turn < max_turns:
        turn += 1
        logger.debug(f"=== Turn {turn} ===")

        start = time.time()

        try:
            response = bedrock_client.converse(
                modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
                messages=messages,
                toolConfig=toolConfig,
                inferenceConfig={
                    "temperature": 0.0
                }
            )

            elapsed = time.time() - start
            logger.debug(f"Claude responded in {elapsed:.2f}s")
            logger.debug(f"Stop reason: {response['stopReason']}")

            # Add Claude's response to messages
            messages.append({
                "role": "assistant",
                "content": response['output']['message']['content']
            })

            # Check stop reason
            if response['stopReason'] == 'end_turn':
                logger.debug("Claude finished!")
                break

            elif response['stopReason'] == 'tool_use':
                # Execute tools
                tool_results = []

                for content_block in response['output']['message']['content']:
                    if 'toolUse' in content_block:
                        tool_use = content_block['toolUse']
                        tool_name = tool_use['name']
                        tool_input = tool_use['input']
                        tool_use_id = tool_use['toolUseId']

                        logger.debug(f"Tool requested: {tool_name}")

                        # Execute the tool
                        tool_input['toolUseId'] = tool_use_id
                        result = await execute_tool(tool_name, tool_input, session, project_root, metrics_tracker)

                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_use_id,
                                "content": result['content']
                            }
                        })

                # Add tool results to conversation
                messages.append({
                    "role": "user",
                    "content": tool_results
                })

            else:
                logger.warning(f"Unexpected stop reason: {response['stopReason']}")
                break

        except Exception as e:
            logger.error(f"Error in agent loop: {e}")
            raise

    # End metrics tracking
    metrics_tracker.end_task()
    metrics = metrics_tracker.get_metrics()

    logger.debug(f"Agent loop completed in {turn} turns")

    return messages, metrics

async def main(verbose=False):
    # Configure logging based on verbose flag
    if verbose:
        logger.add(sys.stderr, level="DEBUG", format="<level>{message}</level>")
    else:
        logger.add(sys.stderr, level="INFO", format="<level>{message}</level>")

    logger.info("Starting Application Signals enablement evaluation\n")

    # Import datetime and Path at the start
    from datetime import datetime

    try:
        bedrock_client = boto3.client(
            service_name='bedrock-runtime',
            region_name='us-east-1'
        )
        logger.debug("Bedrock client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Bedrock client: {e}")
        logger.error("Make sure AWS credentials are configured (aws configure)")
        sys.exit(1)

    tasks_file = Path(__file__).parent / "tasks" / "enablement_tasks.json"
    with open(tasks_file) as f:
        tasks = json.load(f)

    logger.info(f"Loaded {len(tasks)} task(s)")
    for task in tasks:
        logger.info(f"  - {task['id']}: {task['platform']} + {task['language']}")

    logger.info("")

    logger.debug("Connecting to MCP server...")

    async with connect_to_mcp_server(verbose=verbose) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_response = await session.list_tools()
            logger.debug(f"Connected to MCP server with {len(tools_response.tools)} tools")

            for task in tasks:
                logger.info(f"Running: {task['id']}...")
                messages, metrics = await run_agent_loop(bedrock_client, session, task, tools_response.tools)

                # Run validation
                validation_results = await validate_with_llm(bedrock_client, task, task["mock_project_path"])

                # Display clean summary
                logger.info("\n" + "="*60)
                logger.info(f"EVALUATION COMPLETE: {task['id']}")
                logger.info("="*60)
                logger.info(f"Duration: {metrics['task_duration']:.2f}s")
                logger.info(f"Turns: {len([c for c in metrics['tool_calls_detail'] if c['tool_name'] != 'enable_application_signals']) // 2 + 1}")
                logger.info(f"Hit Rate: {metrics['hit_rate']:.1%}")
                logger.info(f"Success Rate: {metrics['success_rate']:.1%}")
                logger.info(f"Unnecessary Tool Calls: {metrics['unnecessary_tool_calls']}")

                # Validation summary
                if validation_results.get("error"):
                    logger.info(f"Validation: ❌ ERROR")
                else:
                    passed = sum(1 for r in validation_results["criteria_results"] if r["status"] == "PASS")
                    total = len(validation_results["criteria_results"])
                    status = "✅ PASS" if validation_results["overall_pass"] else "❌ FAIL"
                    logger.info(f"Validation: {status} ({passed}/{total} criteria met)")

                logger.info("="*60)

                # Generate and save report
                report_content = generate_report(task, metrics, validation_results, task["mock_project_path"])

                reports_dir = Path(__file__).parent / "reports"
                reports_dir.mkdir(exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                report_file = reports_dir / f"enablement_eval_{timestamp}.md"

                with open(report_file, "w") as f:
                    f.write(report_content)

                logger.info(f"\nReport saved to: {report_file}\n")

            await asyncio.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate Application Signals enablement tool"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging (shows all tool calls and MCP server logs)"
    )

    args = parser.parse_args()
    asyncio.run(main(verbose=args.verbose))
