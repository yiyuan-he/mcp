# MCP Tool Evaluation Framework

Generic evaluation framework for testing AI agents using Model Context Protocol (MCP) tools. Provides reusable components for metrics tracking, agent orchestration, and validation.

## Quick Start

### Running Existing Evals

```bash
# Run enablement evaluation (all tasks)
python evals/eval_enablement.py

# Run with verbose logging
python evals/eval_enablement.py -v

# Run specific task without cleanup
python evals/eval_enablement.py --task ec2_python_flask --no-cleanup
```

### CLI Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Enable debug logging |
| `--task TASK_ID` | Run specific task by ID (default: all) |
| `--no-cleanup` | Skip cleanup after evaluation (for inspecting changes) |

---

## Framework Architecture

The framework separates **tool-agnostic** components (reusable) from **tool-specific** logic:

```
evals/
├── framework/                    # Generic (reusable for any MCP tool)
│   ├── metrics.py               # MetricsTracker (hit rate, success rate)
│   ├── mcp_client.py            # MCP connection utilities
│   ├── file_tools.py            # Generic file operations
│   ├── agent.py                 # Multi-turn agent loop
│   └── validation.py            # LLM-as-judge validation
│
├── eval_enablement.py           # Enablement tool eval (example)
└── tasks/
    └── enablement_tasks.json    # Enablement task configs
```

### Generic Framework Components

**MetricsTracker** - Tracks tool-agnostic metrics:
- Hit rate: % of expected tools called
- Success rate: % of successful tool calls
- Task duration, file operation counts

**Agent Loop** - Multi-turn conversation orchestration:
- Sends prompt to LLM
- Handles tool calls (MCP + file operations)
- Configurable max turns (default: 20)

**LLM-as-Judge Validation** - Evaluates results against rubric:
- Takes validation criteria list
- Optional git diff for code changes
- Optional build results
- Returns PASS/FAIL per criterion

**MCP Client** - Connection utilities:
- Connect to any MCP server via stdio
- Convert MCP tools to Bedrock format

---

## Adding Evals for New MCP Tools

### Step 1: Create Task Configuration

Create `evals/tasks/your_tool_tasks.json`:

```json
[
  {
    "id": "task_identifier",
    "description": "Human-readable task description",
    "expected_tools": ["your_mcp_tool"],
    "validation_rubric": [
      "Criterion 1: Expected outcome",
      "Criterion 2: Another requirement"
    ]
  }
]
```

**Core Fields:**
- `id` - Unique task identifier
- `description` - What the task tests
- `expected_tools` - MCP tools agent should call (for hit rate metric)
- `validation_rubric` - Validation criteria (evaluated by LLM)

**Optional Tool-Specific Fields:**
Add any custom fields your tool needs for prompt construction (e.g., `platform`, `language`, `region`, etc.)

### Step 2: Create Eval Script

Create `evals/eval_your_tool.py`:

```python
"""Your MCP Tool Evaluation Script."""

import argparse
import asyncio
import boto3
import json
import sys
from loguru import logger
from pathlib import Path

from framework import (
    MetricsTracker,
    connect_to_mcp_server,
    run_agent_loop,
    validate_with_llm,
)
from mcp import ClientSession

logger.remove()


async def run_task(bedrock_client, session, task, mcp_tools, args):
    """Run a single evaluation task."""
    logger.info(f'Running: {task["id"]}...')

    # 1. Construct tool-specific prompt from task metadata
    prompt = f"""Your task prompt using task fields:
{task['description']}
{task.get('custom_field', '')}
"""

    # 2. Set project root (adjust for your tool)
    project_root = Path.cwd()

    # 3. Run agent loop
    metrics_tracker = MetricsTracker()

    try:
        await run_agent_loop(
            bedrock_client=bedrock_client,
            session=session,
            prompt=prompt,
            project_root=project_root,
            mcp_tools=mcp_tools,
            metrics_tracker=metrics_tracker,
        )

        # 4. Run validation
        validation = await validate_with_llm(
            bedrock_client=bedrock_client,
            validation_rubric=task['validation_rubric'],
            git_diff="",  # Empty for read-only tools
        )

        # 5. Report metrics
        metrics = metrics_tracker.get_metrics(
            expected_tools=task.get('expected_tools', [])
        )

        logger.info('\n' + '=' * 60)
        logger.info(f'EVALUATION COMPLETE: {task["id"]}')
        logger.info('=' * 60)
        logger.info(f'Duration: {metrics["task_duration"]:.2f}s')
        logger.info(f'Hit Rate: {metrics.get("hit_rate", 0):.1%}')
        logger.info(f'Success Rate: {metrics["success_rate"]:.1%}')

        if validation.get('error'):
            logger.info('Validation: ❌ ERROR')
        else:
            passed = sum(1 for r in validation['criteria_results'] if r['status'] == 'PASS')
            total = len(validation['criteria_results'])
            status = '✅ PASS' if validation['overall_pass'] else '❌ FAIL'
            logger.info(f'Validation: {status} ({passed}/{total} criteria met)')

        logger.info('=' * 60 + '\n')

    except Exception as e:
        logger.error(f'Evaluation failed: {e}')


async def main():
    """Entry point."""
    parser = argparse.ArgumentParser(description='Evaluate your MCP tool')
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--task', help='Run specific task by ID')

    args = parser.parse_args()

    if args.verbose:
        logger.add(sys.stderr, level='DEBUG', format='<level>{message}</level>')
    else:
        logger.add(sys.stderr, level='INFO', format='<level>{message}</level>')

    # Initialize Bedrock
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')

    # Load tasks
    tasks_file = Path(__file__).parent / 'tasks' / 'your_tool_tasks.json'
    with open(tasks_file) as f:
        all_tasks = json.load(f)

    if args.task:
        all_tasks = [t for t in all_tasks if t['id'] == args.task]

    # Connect to MCP server
    async with connect_to_mcp_server(
        server_module='awslabs.your_mcp_server.server',
        verbose=args.verbose
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()

            for task in all_tasks:
                await run_task(bedrock_client, session, task, tools.tools, args)


if __name__ == '__main__':
    asyncio.run(main())
```

### Example: Read-Only Tool

For tools like `list_monitored_services` that only retrieve data:

**Task config:**
```json
{
  "id": "list_services_basic",
  "description": "List all monitored services in us-east-1",
  "region": "us-east-1",
  "expected_tools": ["list_monitored_services"],
  "validation_rubric": [
    "Tool was called successfully",
    "Response contains service list",
    "Response format is valid"
  ]
}
```

**Key points:**
- No git cleanup needed
- Validation checks response content, not code changes
- Simple rubric focusing on API response

### Example: Code-Modifying Tool

For tools like `get_enablement_guide` that modify infrastructure:

**Task config:**
```json
{
  "id": "enable_signals_ec2",
  "description": "Enable Application Signals on EC2",
  "platform": "ec2",
  "language": "python",
  "iac_directory": "infrastructure/ec2/cdk",
  "app_directory": "sample-apps/python/flask",
  "expected_tools": ["get_enablement_guide"],
  "modifies_code": true,
  "build_config": {
    "command": "npm run build",
    "working_dir": "infrastructure/ec2/cdk",
    "install_command": "npm install"
  },
  "validation_rubric": [
    "IAM: CloudWatchAgentServerPolicy attached",
    "CloudWatch Agent: Installed and configured",
    "Build: IaC compiles successfully"
  ]
}
```

**Key points:**
- `modifies_code: true` indicates code changes expected
- `build_config` for compilation validation
- Tool-specific cleanup logic (see enablement example)
- Validation checks git diff

---

## Enablement Tool Example

The `eval_enablement.py` demonstrates a complete code-modifying tool evaluation:

### How It Works

1. **Agent Loop**: AI calls `get_enablement_guide`, reads instructions, modifies IaC/app files
2. **Build Validation**: Runs `npm run build` to verify IaC compiles
3. **LLM-as-Judge**: Evaluates git diff against 14-point rubric
4. **Cleanup**: Resets git state in IaC and app directories (enablement-specific)

### Task Configuration

```json
{
  "id": "ec2_python_flask",
  "platform": "ec2",
  "language": "python",
  "framework": "flask",
  "iac_directory": "infrastructure/ec2/cdk",
  "app_directory": "sample-apps/python/flask",
  "expected_tools": ["get_enablement_guide"],
  "modifies_code": true,
  "build_config": {
    "command": "npm run build",
    "working_dir": "infrastructure/ec2/cdk",
    "install_command": "npm install"
  },
  "validation_rubric": [
    "IAM: CloudWatchAgentServerPolicy is attached to EC2 instance role",
    "Prerequisites: System dependencies installed (wget, docker, python3-pip)",
    "CloudWatch Agent: Downloaded, installed, and configured with application_signals",
    "ADOT: aws-opentelemetry-distro installed via pip3 in UserData",
    "OTel Config: Basic exporters set (OTEL_METRICS_EXPORTER=none, etc.)",
    "Build: IaC compiles successfully (npm run build passes)",
    "Code Integrity: Only IaC/Dockerfile modified, application code unchanged"
  ]
}
```

### Git Cleanup (Enablement-Specific)

The enablement eval includes a `cleanup_enablement_changes()` function that:
- Resets changes in `iac_directory` and `app_directory`
- Runs `git checkout HEAD` and `git clean -fd` on those paths
- Skipped if `--no-cleanup` flag is set

**Note:** Git cleanup is NOT part of the generic framework - implement it in your tool-specific eval if needed.

---

## Validation Rubric Best Practices

**Be specific:**
```json
✅ "IAM: CloudWatchAgentServerPolicy attached to instance role"
❌ "IAM configured correctly"
```

**Use category prefixes:**
```json
"IAM: ...",
"OTel Config: ...",
"Build: ...",
"Response Format: ..."
```

**Handle conditionals explicitly:**
```json
"Dockerfile (if Docker): Uses opentelemetry-instrument wrapper"
```

**Include build validation:**
```json
"Build: IaC compiles successfully (npm run build passes)"
```

---

## Metrics Output

All evals report:

```
============================================================
EVALUATION COMPLETE: ec2_python_flask
============================================================
Duration: 45.32s
Hit Rate: 100.0%                    # Expected tools called
Success Rate: 95.0%                 # Successful tool invocations
File Operations: 12                 # read/write/list count
Validation: ✅ PASS (14/14 criteria met)
============================================================
```

---

## Troubleshooting

**MCP connection fails:**
- Verify `server_module` path in `connect_to_mcp_server()`
- Check MCP server is installed: `python -m awslabs.your_server.server`
- Use `--verbose` to see connection logs

**Build validation fails (code-modifying tools):**
- Verify syntax with local build command
- Check `build_config.working_dir` path is correct
- Ensure dependencies installed

**Validation inconsistent:**
- Review rubric criteria (be more specific)
- Use `--no-cleanup` to inspect `git diff`
- Add `-v` for debug logging

**Agent doesn't call expected tools:**
- Check prompt clarity (does it explain when to use the tool?)
- Review hit_rate metric in output
- Look at `missing_expected_tools` in verbose logs

---

## Framework Design Principles

1. **Generic by default**: Framework components work for any MCP tool
2. **Extend for specifics**: Tool-specific logic lives in eval scripts, not framework
3. **Composable**: Pick what you need (metrics, agent loop, validation)
4. **No magic**: Explicit task configuration, no hidden assumptions
