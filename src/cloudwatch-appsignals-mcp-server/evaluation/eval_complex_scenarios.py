"""
Run complex multi-tool data evaluation tasks.

Complex tasks test realistic root cause analysis scenarios requiring multiple
tool calls, data synthesis, and comprehensive diagnosis.

Usage:
    python run_complex_data_evals.py
    python run_complex_data_evals.py --verbose
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import boto3
from loguru import logger

from lib import MetricsTracker, grade_answer, generate_report, load_fixtures_for_task

# Logger will be configured after parsing command line args
logger.remove()


def get_bedrock_tools(expected_tools):
    """Convert expected tool names to Bedrock tool format."""
    bedrock_tools = []

    # Tool definitions for all possible tools
    tool_schemas = {
        "audit_services": {
            "name": "audit_services",
            "description": "Comprehensive service health audit with root cause analysis, SLO compliance, dependency analysis, and actionable recommendations",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "service_targets": {
                        "type": "string",
                        "description": "JSON array of service targets to audit"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time for audit period"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time for audit period"
                    }
                }
            }
        },
        "get_slo": {
            "name": "get_slo",
            "description": "Get detailed SLO configuration, current attainment, and breach status",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slo_name": {
                        "type": "string",
                        "description": "Name of the SLO"
                    }
                },
                "required": ["slo_name"]
            }
        },
        "query_service_metrics": {
            "name": "query_service_metrics",
            "description": "Query CloudWatch metrics for service performance analysis including latency, error rates, and trends over time",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Name of the service"
                    },
                    "environment": {
                        "type": "string",
                        "description": "Service environment"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time for metrics query"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time for metrics query"
                    }
                },
                "required": ["service_name", "environment"]
            }
        },
        "search_transaction_spans": {
            "name": "search_transaction_spans",
            "description": "Query OpenTelemetry spans data for detailed trace analysis, error investigation, and performance debugging",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "CloudWatch Logs Insights query for spans data"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time for query"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time for query"
                    }
                },
                "required": ["query"]
            }
        },
        "get_service_detail": {
            "name": "get_service_detail",
            "description": "Get detailed information about a specific service including metrics, operations, and dependencies",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Name of the service"
                    },
                    "environment": {
                        "type": "string",
                        "description": "Service environment (e.g., 'eks:production')"
                    }
                },
                "required": ["service_name", "environment"]
            }
        },
    }

    for tool_name in expected_tools:
        if tool_name in tool_schemas:
            schema = tool_schemas[tool_name]
            bedrock_tools.append({
                "toolSpec": {
                    "name": schema["name"],
                    "description": schema["description"],
                    "inputSchema": {
                        "json": schema["inputSchema"]
                    }
                }
            })

    return bedrock_tools


async def execute_tool_with_fixture(tool_name, tool_input, fixtures, expected_tools, metrics_tracker):
    """Execute a tool call by returning fixture data."""
    import time
    start = time.time()
    success = True
    error = None

    try:
        # Get fixture for this tool
        if tool_name not in fixtures:
            error = f"No fixture defined for tool: {tool_name}"
            success = False
            return {
                "toolUseId": tool_input.get("toolUseId", ""),
                "content": [{"text": error}],
                "status": "error"
            }

        fixture_data = fixtures[tool_name]

        # Handle multiple fixtures for the same tool
        if isinstance(fixture_data, list):
            if fixture_data:
                current_fixture = fixture_data.pop(0)
            else:
                error = f"No more fixtures available for tool: {tool_name}"
                success = False
                return {
                    "toolUseId": tool_input.get("toolUseId", ""),
                    "content": [{"text": error}],
                    "status": "error"
                }
        else:
            current_fixture = fixture_data

        # Return fixture as tool response
        return {
            "toolUseId": tool_input.get("toolUseId", ""),
            "content": [{"text": json.dumps(current_fixture, indent=2)}]
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
        # Record metrics
        duration = time.time() - start
        params_to_log = {k: v for k, v in tool_input.items() if k != "toolUseId"}
        metrics_tracker.record_tool_call(tool_name, params_to_log, duration, success, error)
        # Mark if this was an expected tool call
        if metrics_tracker.tool_calls:
            metrics_tracker.tool_calls[-1]["is_expected"] = tool_name in expected_tools


async def run_agent_loop(bedrock_client, task, fixtures):
    """Run the agent loop with fixture-based tool responses."""

    # Initialize metrics tracker
    metrics_tracker = MetricsTracker()
    metrics_tracker.start_task()

    prompt = task["prompt"]

    logger.debug(f"Sending prompt to Claude: {prompt[:100]}...")

    # Build tool config
    bedrock_tools = get_bedrock_tools(task["expected_tools"])
    toolConfig = {"tools": bedrock_tools}
    logger.debug(f"Configured {len(bedrock_tools)} tools for Claude")

    # Start conversation
    messages = [
        {
            "role": "user",
            "content": [{"text": prompt}]
        }
    ]

    max_turns = 15  # More turns for complex tasks
    turn = 0
    final_answer = None

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
                # Extract final answer from last message
                for content in response['output']['message']['content']:
                    if 'text' in content:
                        final_answer = content['text']
                logger.debug("Claude finished!")
                break

            elif response['stopReason'] == 'tool_use':
                # Execute tools with fixtures
                tool_results = []

                for content_block in response['output']['message']['content']:
                    if 'toolUse' in content_block:
                        tool_use = content_block['toolUse']
                        tool_name = tool_use['name']
                        tool_input = tool_use['input']
                        tool_use_id = tool_use['toolUseId']

                        logger.debug(f"Tool requested: {tool_name}")

                        # Execute the tool with fixture
                        tool_input['toolUseId'] = tool_use_id
                        result = await execute_tool_with_fixture(
                            tool_name,
                            tool_input,
                            fixtures,
                            task["expected_tools"],
                            metrics_tracker
                        )

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
    metrics = metrics_tracker.get_metrics(expected_tools=task["expected_tools"])

    logger.debug(f"Agent loop completed in {turn} turns")

    return final_answer, metrics


async def main(verbose=False):
    # Configure logging based on verbose flag
    if verbose:
        logger.add(sys.stderr, level="DEBUG", format="<level>{message}</level>")
    else:
        logger.add(sys.stderr, level="INFO", format="<level>{message}</level>")

    logger.info("Running COMPLEX DATA evaluation tasks (multi-tool RCA scenarios)\n")

    # Initialize Bedrock client
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

    # Load tasks
    tasks_file = Path(__file__).parent / "tasks" / "complex" / "data_tool_tasks_complex.json"
    with open(tasks_file) as f:
        tasks = json.load(f)

    logger.info(f"Loaded {len(tasks)} complex task(s)")
    for task in tasks:
        logger.info(f"  - {task['id']}: {task['expected_tools']}")

    logger.info("")

    # Load fixtures
    fixtures_dir = Path(__file__).parent / "fixtures"

    for task in tasks:
        logger.info(f"Running: {task['id']}...")

        # Load fixtures for this task
        fixtures = load_fixtures_for_task(task, fixtures_dir)

        # Run agent loop
        agent_answer, metrics = await run_agent_loop(bedrock_client, task, fixtures)

        # Grade the answer
        grading_result = await grade_answer(bedrock_client, task, agent_answer)

        # Display clean summary
        logger.info("\n" + "="*60)
        logger.info(f"EVALUATION COMPLETE: {task['id']}")
        logger.info("="*60)
        logger.info(f"Duration: {metrics['task_duration']:.2f}s")
        logger.info(f"Tool Calls: {metrics['tool_call_count']}")
        logger.info(f"Hit Rate: {metrics['hit_rate']:.1%} ({len(metrics.get('expected_tools_called', []))}/{len(task['expected_tools'])} expected tools)")
        logger.info(f"Expected Tools: {', '.join(metrics.get('expected_tools_called', [])) or 'None'}")
        if metrics.get('unexpected_tools_called'):
            logger.info(f"Unexpected Tools: {', '.join(metrics['unexpected_tools_called'])}")
        logger.info(f"Success Rate: {metrics['success_rate']:.1%}")
        logger.info(f"Grading: {'✅ PASS' if grading_result['passed'] else '❌ FAIL'} ({grading_result['method']})")
        logger.info("="*60)

        # Generate and save report
        from datetime import datetime
        report_content = generate_report(task, agent_answer, grading_result, metrics, report_type="data_tool")

        reports_dir = Path(__file__).parent / "reports"
        reports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = reports_dir / f"complex_data_eval_{timestamp}.md"

        with open(report_file, "w") as f:
            f.write(report_content)

        logger.info(f"\nReport saved to: {report_file}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run complex multi-tool data evaluation tasks"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging"
    )

    args = parser.parse_args()
    asyncio.run(main(verbose=args.verbose))
