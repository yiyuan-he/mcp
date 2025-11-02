# MCP Evaluation Framework

A framework for evaluating MCP tool performance using multi-turn agent interactions with LLM-as-a-judge validation.

## What It Does

Tests MCP tools by running Claude as an agent through multi-turn conversations, capturing tool calls and outputs, and validating results against defined rubrics using LLM judges.

## Prerequisites

- Python 3.10+
- AWS credentials configured (for Bedrock access)
- Your MCP server installed and accessible

## Quick Start

```bash
# List available tasks
python -m evals applicationsignals --list

# Run all tasks
python -m evals applicationsignals

# Run specific task module
python -m evals applicationsignals --task investigation_tasks

# Run specific task by ID
python -m evals applicationsignals --task-id basic_service_health

# Verbose output
python -m evals applicationsignals -v
```

## Example Output

```
Running task: basic_service_health
✓ Prompt 1/1 passed
  Validation: LLMJudgeValidator
    ✓ Identifies service health status clearly
    ✓ Calls appropriate audit tools
  Metrics:
    - Duration: 12.3s
    - Tool calls: 3
    - Hit rate: 100% (all expected tools called)

Task Result: PASS
```

## Adding a New Task

Create a task directory under `evals/` named after your MCP server (e.g., `evals/filesystem/`, `evals/slack/`) and add a task file:

```python
# evals/<your-server-name>/investigation_tasks.py
from pathlib import Path
from evals.core import Task

class MyCustomTask(Task):
    def __init__(self):
        super().__init__(
            id='my_custom_task',
            expected_tools=['tool_name'],  # MCP tools you expect to be called
            max_turns=15  # Maximum conversation turns
        )

    def get_prompts(self, context):
        """Return the prompt(s) to give the agent"""
        return ["Analyze the health of my payment service"]

    @property
    def rubric(self):
        """Return validation criteria"""
        return [
            "Identifies key service metrics",
            "Provides actionable insights",
            "Calls relevant monitoring tools"
        ]

# Export your tasks
TASKS = [MyCustomTask()]

# Specify the path to your MCP server
SERVER_PATH = Path(__file__).parent.parent.parent / 'path' / 'to' / 'your' / 'server.py'
```

Then run:
```bash
# Run specific task
python -m evals <your-server-name> --task-id my_custom_task

# Run all tasks in a module
python -m evals <your-server-name> --task investigation_tasks

# Run all tasks
python -m evals <your-server-name>
```

See `evals/applicationsignals/investigation_tasks.py` and `enablement_tasks.py` for more examples.

## Mocking AWS APIs

To make tests deterministic, you can mock AWS API responses by adding a `get_mocks()` method to your task.

### Setup Fixtures Directory

First, define a fixtures directory at the top of your task file:

```python
# evals/mytool/my_tasks.py
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / 'fixtures'
```

Then create your fixture files in `evals/mytool/fixtures/`.

### Add Mocking to Task

```python
class MyCustomTask(Task):
    # ... other methods ...

    def get_mocks(self):
        return {
            'boto3': {
                'cloudwatch': {
                    # Inline response data
                    'GetMetricData': {
                        'MetricDataResults': [
                            {
                                'Id': 'latency',
                                'Values': [120.5, 135.2, 98.3],
                                'Timestamps': ['2024-01-01T00:00:00Z', ...]
                            }
                        ]
                    },
                    # Or reference a fixture file
                    'DescribeAlarms': str(FIXTURES_DIR / 'my_alarms.json')
                },
                'application-signals': {
                    'list_audit_findings': str(FIXTURES_DIR / 'healthy_service.json')
                }
            }
        }
```

**Mock structure:**
- First level: library name (`'boto3'`)
- Second level: service name (`'cloudwatch'`, `'application-signals'`, etc.)
- Third level: operation name → response data (dict or path to JSON fixture)

See `evals/applicationsignals/fixtures/investigation/` for example fixture files.

## Troubleshooting

**Server not found:** Ensure `SERVER_PATH` in your task file points to your MCP server.

**AWS credentials not configured:** Run `aws configure` to set up Bedrock access.

**Task hangs:** Check the `max_turns` setting - the agent may need more turns to complete the task.
