"""
Evaluate list_monitored_services tool.

Tests basic service listing, filtering, and data interpretation capabilities.

Usage:
    python eval_list_monitored_services.py
    python eval_list_monitored_services.py --verbose
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


def get_bedrock_tools():
    """Get tool schema for list_monitored_services."""
    return [{
        "toolSpec": {
            "name": "list_monitored_services",
            "description": "Get a comprehensive overview of all monitored services in Application Signals",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 100)"
                        }
                    }
                }
            }
        }
    }]


async def execute_tool_with_fixture(tool_name, tool_input, fixtures, expected_tools, metrics_tracker):
    """Execute a tool call by returning fixture data."""
    import time
    start = time.time()
    success = True
    error = None

    try:
        if tool_name not in fixtures:
            error = f"No fixture defined for tool: {tool_name}"
            success = False
            return {
                "toolUseId": tool_input.get("toolUseId", ""),
                "content": [{"text": error}],
                "status": "error"
            }

        fixture_data = fixtures[tool_name]
        return {
            "toolUseId": tool_input.get("toolUseId", ""),
            "content": [{"text": json.dumps(fixture_data, indent=2)}]
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
        duration = time.time() - start
        params_to_log = {k: v for k, v in tool_input.items() if k != "toolUseId"}
        metrics_tracker.record_tool_call(tool_name, params_to_log, duration, success, error)
        if metrics_tracker.tool_calls:
            metrics_tracker.tool_calls[-1]["is_expected"] = tool_name in expected_tools


async def run_agent_loop(bedrock_client, task, fixtures):
    """Run the agent loop with fixture-based tool responses."""
    metrics_tracker = MetricsTracker()
    metrics_tracker.start_task()

    prompt = task["prompt"]
    logger.debug(f"Sending prompt to Claude: {prompt[:100]}...")

    bedrock_tools = get_bedrock_tools()
    toolConfig = {"tools": bedrock_tools}

    messages = [{"role": "user", "content": [{"text": prompt}]}]
    max_turns = 10
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
                inferenceConfig={"temperature": 0.0}
            )

            elapsed = time.time() - start
            logger.debug(f"Claude responded in {elapsed:.2f}s")
            logger.debug(f"Stop reason: {response['stopReason']}")

            messages.append({
                "role": "assistant",
                "content": response['output']['message']['content']
            })

            if response['stopReason'] == 'end_turn':
                for content in response['output']['message']['content']:
                    if 'text' in content:
                        final_answer = content['text']
                logger.debug("Claude finished!")
                break

            elif response['stopReason'] == 'tool_use':
                tool_results = []
                for content_block in response['output']['message']['content']:
                    if 'toolUse' in content_block:
                        tool_use = content_block['toolUse']
                        tool_name = tool_use['name']
                        tool_input = tool_use['input']
                        tool_use_id = tool_use['toolUseId']

                        logger.debug(f"Tool requested: {tool_name}")

                        tool_input['toolUseId'] = tool_use_id
                        result = await execute_tool_with_fixture(
                            tool_name, tool_input, fixtures, task["expected_tools"], metrics_tracker
                        )

                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_use_id,
                                "content": result['content']
                            }
                        })

                messages.append({"role": "user", "content": tool_results})
            else:
                logger.warning(f"Unexpected stop reason: {response['stopReason']}")
                break

        except Exception as e:
            logger.error(f"Error in agent loop: {e}")
            raise

    metrics_tracker.end_task()
    metrics = metrics_tracker.get_metrics(expected_tools=task["expected_tools"])
    logger.debug(f"Agent loop completed in {turn} turns")

    return final_answer, metrics


async def main(verbose=False):
    if verbose:
        logger.add(sys.stderr, level="DEBUG", format="<level>{message}</level>")
    else:
        logger.add(sys.stderr, level="INFO", format="<level>{message}</level>")

    logger.info("Evaluating: list_monitored_services\n")

    # Initialize Bedrock client
    try:
        bedrock_client = boto3.client(service_name='bedrock-runtime', region_name='us-east-1')
        logger.debug("Bedrock client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Bedrock client: {e}")
        logger.error("Make sure AWS credentials are configured (aws configure)")
        sys.exit(1)

    # Load tasks
    tasks_file = Path(__file__).parent / "tasks" / "tools" / "list_monitored_services.json"
    with open(tasks_file) as f:
        tasks = json.load(f)

    logger.info(f"Loaded {len(tasks)} task(s) for list_monitored_services")
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
        logger.info(f"Hit Rate: {metrics['hit_rate']:.1%}")
        logger.info(f"Success Rate: {metrics['success_rate']:.1%}")
        logger.info(f"Grading: {'✅ PASS' if grading_result['passed'] else '❌ FAIL'} ({grading_result['method']})")
        logger.info("="*60)

        # Generate and save report
        from datetime import datetime
        report_content = generate_report(task, agent_answer, grading_result, metrics, report_type="data_tool")

        reports_dir = Path(__file__).parent / "reports"
        reports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = reports_dir / f"list_monitored_services_eval_{timestamp}.md"

        with open(report_file, "w") as f:
            f.write(report_content)

        logger.info(f"\nReport saved to: {report_file}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate list_monitored_services tool")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose/debug logging")
    args = parser.parse_args()
    asyncio.run(main(verbose=args.verbose))
