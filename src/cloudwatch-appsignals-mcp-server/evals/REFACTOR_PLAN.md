# MCP Eval Framework Refactor Plan

## Executive Summary

This document outlines the refactor of the MCP evaluation framework to address PR #1618 feedback. The goal is to create an **extensible, modular evaluation framework** that supports diverse MCP tool testing scenarios beyond just code modification.

**Key Changes:**
1. **Explicit Captor/Validator Pattern** - Separate output capture from validation logic
2. **Simple Mock System** - Dict-based mocking with AWS API response structure
3. **Local MCP Server Testing** - Always test local changes, not installed packages
4. **Clear Modularity** - Generic framework separate from MCP-specific code
5. **Multi-Prompt Support** - Test agent behavior across multiple sequential prompts

**Timeline:** ~2-3 weeks for full implementation

---

## Table of Contents

1. [Current State & Problems](#current-state--problems)
2. [Goals & Requirements](#goals--requirements)
3. [Architecture Overview](#architecture-overview)
4. [File Structure](#file-structure)
5. [Detailed Design](#detailed-design)
6. [Usage Examples](#usage-examples)
7. [Implementation Plan](#implementation-plan)
8. [Migration Guide](#migration-guide)
9. [Success Criteria](#success-criteria)
10. [Q&A](#questions--answers)
11. [Appendix](#appendix-quick-reference)

---

## Current State & Problems

### What Exists Today

```
evals/
├── framework/
│   ├── agent.py           # Multi-turn agent loop
│   ├── validation.py      # LLM-as-judge validation
│   ├── metrics.py         # Hit rate, success rate
│   ├── mcp_client.py      # MCP connection
│   ├── constants.py       # Prompts and config
│   └── file_tools.py      # File operations
└── eval_enablement.py     # Enablement tool eval
```

### Problems (From PR #1618 Review)

**From reviewer (thpierce):**

1. **Tight Coupling** - Validation assumes code modification (git diff only)
   - Can't easily test data interpretation tasks
   - Can't easily test workflow/conversation tasks

2. **Task-Specific Constants** - `ENABLEMENT_TASK_PROMPT` in framework
   - Generic framework shouldn't have task-specific prompts
   - Move to eval scripts

3. **Module Import for MCP** - Tests installed package, not local changes
   - `python -m awslabs.cloudwatch_appsignals_mcp_server.server` uses site-packages
   - Developer makes local change → eval tests old code → confusion

4. **No Mocking** - Can't test without real AWS infrastructure
   - Slow, expensive, unreliable
   - Can't test edge cases easily

5. **Limited Extensibility** - Hard to add new eval types
   - Need captors/validators pattern
   - Support different output types (code, data, workflows)

---

## Goals & Requirements

### From PR Reviewer (thpierce)

> "Keep a close eye on extensibility and modularity. Draw boundaries - anything specific to our MCP should not live in framework."

**Requirements:**
- ✅ Separate generic framework from MCP-specific code
- ✅ Support multiple eval types (code modification, data interpretation, workflows)
- ✅ Implement captors/validators pattern for reusability
- ✅ Mock AWS clients used inside MCP server with simple code
- ✅ Test local MCP server code, not installed packages
- ✅ Move task-specific prompts out of framework

### Design Principles

1. **Simple User API** - Minimal code for eval authors
2. **Composable** - Mix and match captors/validators
3. **Convention over Configuration** - Sensible defaults
4. **Extensible** - Easy to add new components
5. **Explicit** - No magic, clear configuration

---

## Architecture Overview

### The 4-Layer Model

```
┌─────────────────────────────────────────────────────────────┐
│                         EvalRunner                          │
│              (Orchestrates everything)                      │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
   ┌─────────┐          ┌──────────┐         ┌──────────┐
   │  TASK   │          │ CAPTORS  │         │VALIDATORS│
   │         │          │          │         │          │
   │ Prompts │          │ GitDiff  │         │ LLMJudge │
   │ Rubric  │          │ ToolCall │         │ Build    │
   │ Mocks   │          │ Response │         │ Sequence │
   └─────────┘          └──────────┘         └──────────┘
```

### How Layers Work Together

**Flow:**
1. **Task** defines what to test (prompts, rubric, mocks)
2. **EvalRunner** executes agent with prompts
3. **Captors** observe outputs (git diff, tool calls, responses)
4. **Validators** evaluate outputs against rubric
5. **EvalRunner** reports results

**Key Insight:** Separation of concerns enables composition.
- Different tasks → same captors/validators
- Same task → different validators for different criteria
- Code changes easily isolated to one layer

---

## File Structure

### Target Architecture

```
evals/
├── framework/                          # Generic, reusable
│   ├── core.py                        # Task, Captor, Validator base classes
│   ├── runner.py                      # EvalRunner orchestration
│   │
│   ├── captors/                       # Output capture
│   │   ├── __init__.py
│   │   ├── base.py                    # Captor ABC
│   │   ├── git_diff.py                # GitDiffCaptor
│   │   ├── tool_calls.py              # ToolCallsCaptor
│   │   ├── conversation.py            # ConversationCaptor
│   │   ├── final_response.py          # FinalResponseCaptor
│   │   └── tool_results.py            # ToolResultsCaptor
│   │
│   ├── validators/                    # Output validation
│   │   ├── __init__.py
│   │   ├── base.py                    # Validator ABC
│   │   ├── llm_judge.py               # LLMJudgeValidator
│   │   ├── build.py                   # BuildValidator
│   │   ├── tool_sequence.py           # ToolSequenceValidator
│   │   └── prompts.py                 # Validation prompts (code, data, workflow)
│   │
│   ├── mocking/                       # Mock system
│   │   ├── __init__.py
│   │   ├── base.py                    # MockHandler ABC, MockHandlerRegistry
│   │   ├── helpers.py                 # capture_boto3_response()
│   │   └── handlers/
│   │       ├── __init__.py
│   │       └── boto3_handler.py       # Boto3MockHandler
│   │
│   ├── mcp/                           # MCP-specific (isolated!)
│   │   ├── __init__.py
│   │   ├── client.py                  # connect_to_mcp_server()
│   │   └── mock_server_wrapper.py     # Applies mocks in subprocess
│   │
│   ├── agent.py                       # Agent loop (refactored)
│   └── metrics.py                     # Metrics calculation
│
├── eval_enablement.py                 # Enablement tool eval
├── eval_audit_services.py             # Audit tool eval (future)
├── eval_root_cause.py                 # Root cause eval (future)
│
├── fixtures/                          # Mock data files
│   ├── cloudwatch/
│   │   ├── metric_spike.json
│   │   └── normal_metrics.json
│   ├── ce/
│   │   └── anomalies.json
│   └── xray/
│       └── traces.json
│
├── docs/
│   ├── MOCK_REFERENCE.md              # Quick reference
│   └── MOCK_HANDLER_TEMPLATE.md       # Extension guide
│
└── REFACTOR_PLAN.md                   # This document
```

---

## Detailed Design

### 1. Task Base Class

```python
# framework/core.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class Task(ABC):
    """Base class for evaluation tasks."""

    id: str
    max_turns: int = 20

    @abstractmethod
    def get_prompt(self) -> list[str]:
        """Return task prompt(s) for the agent.

        Returns:
            List of prompts sent sequentially to the agent.
            - Single prompt: ["prompt"]
            - Multi-step: ["step1", "step2", "step3"]

        Examples:
            # Single prompt
            def get_prompt(self):
                return ["Investigate the database issue"]

            # Multi-step investigation
            def get_prompt(self):
                return [
                    "What services are having issues?",
                    "Focus on the database - what's wrong?",
                    "What's the root cause?"
                ]
        """
        pass

    @property
    @abstractmethod
    def rubric(self) -> list[str]:
        """Return validation criteria.

        Each string is a criterion the agent must meet.

        Examples:
            ["Agent identified the root cause",
             "Agent suggested a fix"]
        """
        pass

    def get_mocks(self) -> Optional[dict]:
        """Return mock specification for AWS API calls.

        Returns:
            Dict with structure matching AWS API responses, or None.

            {
                'boto3': {
                    'service_name': {
                        'OperationName': {...}  # Inline AWS response
                        # OR
                        'OperationName': 'fixtures/file.json'  # File reference
                    }
                }
            }

        Examples:
            # No mocking
            def get_mocks(self):
                return None

            # Inline mock
            def get_mocks(self):
                return {
                    'boto3': {
                        'cloudwatch': {
                            'GetMetricData': {
                                "MetricDataResults": [{"Values": [1, 2, 3]}]
                            }
                        }
                    }
                }

            # File reference
            def get_mocks(self):
                return {
                    'boto3': {
                        'ce': {
                            'GetAnomalies': 'fixtures/ce/anomalies.json'
                        }
                    }
                }
        """
        return None

    def get_captors(self) -> list['Captor']:
        """Define what to capture during execution.

        Override to customize. Default captures common outputs.

        Returns:
            List of Captor instances
        """
        from .captors import GitDiffCaptor, ToolCallsCaptor, ConversationCaptor
        return [
            GitDiffCaptor(),
            ToolCallsCaptor(),
            ConversationCaptor(),
        ]

    def get_validators(self) -> list['Validator']:
        """Define how to validate captured outputs.

        Override to customize validation strategy.

        Returns:
            List of Validator instances
        """
        from .validators import LLMJudgeValidator
        return [
            LLMJudgeValidator(
                rubric=self.rubric,
                input_from=['git_diff']  # Default assumes code changes
            )
        ]

    @property
    def expected_tools(self) -> list[str]:
        """Expected tools for hit rate calculation.

        Returns:
            List of tool names expected to be called
        """
        return []
```

### 2. Captor Base Class

```python
# framework/captors/base.py
from abc import ABC, abstractmethod
from typing import Any

class Captor(ABC):
    """Base class for output captors.

    Captors extract specific outputs from agent execution.
    They observe but don't modify or evaluate.
    """

    @property
    @abstractmethod
    def output_key(self) -> str:
        """Key to store captured data under in results dict.

        Example: 'git_diff', 'tool_calls', 'final_response'
        """
        pass

    @abstractmethod
    async def capture(self, context: 'EvalContext') -> Any:
        """Capture output from evaluation run.

        Args:
            context: Evaluation context with agent results, project_root, etc.

        Returns:
            Captured data (any type appropriate for this captor)
        """
        pass
```

### 3. Example Captor Implementation

```python
# framework/captors/git_diff.py
from .base import Captor
import subprocess
from pathlib import Path

class GitDiffCaptor(Captor):
    """Captures git diff of changes made during task execution."""

    @property
    def output_key(self) -> str:
        return 'git_diff'

    async def capture(self, context: 'EvalContext') -> str:
        """Get git diff from project root.

        Returns:
            Git diff as string
        """
        result = subprocess.run(
            ['git', 'diff'],
            cwd=context.project_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout
```

### 4. Validator Base Class

```python
# framework/validators/base.py
from abc import ABC, abstractmethod
from typing import Any, Dict

class Validator(ABC):
    """Base class for validators.

    Validators evaluate captured outputs against criteria.
    """

    def __init__(self, output_metric: str = None):
        """Initialize validator.

        Args:
            output_metric: Name for this validator's metric in results.
                          Defaults to class name if not provided.
        """
        self.output_metric = output_metric or self.__class__.__name__

    @abstractmethod
    async def validate(self, captured_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate captured data.

        Args:
            captured_data: Dict with all captured outputs from captors.
                          Keys are captor output_key values.

        Returns:
            Dict with validation results:
            {
                'passed': bool,          # Required: Did validation pass?
                'score': float,          # Optional: Numeric score
                'details': dict,         # Optional: Additional details
                'reasoning': str         # Optional: Explanation
            }

        Examples:
            # Binary pass/fail
            return {'passed': True, 'reasoning': 'All criteria met'}

            # With score
            return {
                'passed': True,
                'score': 0.85,
                'details': {'criteria_met': 4, 'criteria_total': 5}
            }
        """
        pass
```

### 5. Mock System

#### User API (Simple Dict)

```python
# User code - just return a dict
def get_mocks(self):
    return {
        'boto3': {
            'cloudwatch': {
                # Inline data (small responses)
                'PutMetricAlarm': {
                    'ResponseMetadata': {'HTTPStatusCode': 200}
                },

                # File reference (large responses)
                'GetMetricData': 'fixtures/cloudwatch/metrics.json'
            },
            'ce': {
                'GetAnomalies': 'fixtures/ce/anomalies.json'
            }
        }
    }
```

#### How to Create Mocks

**Rule:** Mock structure = AWS API response structure

**Method 1: Copy from AWS Docs**
1. Google: "AWS CloudWatch GetMetricData API"
2. Find "Response Syntax" section
3. Copy-paste into your mock

**Method 2: Capture Real Response (Recommended)**
```python
from framework.mocking.helpers import capture_boto3_response

# Make real API call once, save response
capture_boto3_response(
    service='ce',
    operation='get_anomalies',
    DateInterval={'StartDate': '2024-01-01', 'EndDate': '2024-01-31'}
)
# Output: ✓ Saved to fixtures/ce/get_anomalies.json

# Then use:
def get_mocks(self):
    return {
        'boto3': {
            'ce': {
                'GetAnomalies': 'fixtures/ce/get_anomalies.json'
            }
        }
    }
```

#### MockHandler Base Class

```python
# framework/mocking/base.py
from abc import ABC, abstractmethod
from pathlib import Path
import json

class MockHandler(ABC):
    """Base class for library-specific mock handlers."""

    @abstractmethod
    def patch(self, mock_config: dict, base_path: Path):
        """Apply patches for this library.

        Args:
            mock_config: Configuration dict for this mock type
            base_path: Base directory for resolving fixture file paths
        """
        pass

    @abstractmethod
    def unpatch(self):
        """Remove all patches and restore original functionality."""
        pass

    def resolve_fixture(self, value, base_path: Path):
        """Resolve a value that might be a fixture file reference.

        Args:
            value: Either dict/list (inline data) or str (file path)
            base_path: Base directory for relative paths

        Returns:
            Resolved data (always dict or list)

        Raises:
            FileNotFoundError: If fixture file doesn't exist
            TypeError: If value is not dict, list, or str
        """
        if isinstance(value, (dict, list)):
            return value

        if isinstance(value, str):
            file_path = base_path / value
            if not file_path.exists():
                raise FileNotFoundError(f"Fixture file not found: {file_path}")
            with open(file_path) as f:
                return json.load(f)

        raise TypeError(f"Expected dict, list, or string, got {type(value)}")
```

#### Boto3 Mock Handler

```python
# framework/mocking/handlers/boto3_handler.py
from ..base import MockHandler
from unittest.mock import MagicMock
from collections import defaultdict
import boto3
from pathlib import Path

class Boto3MockHandler(MockHandler):
    """Mock handler for boto3 AWS SDK.

    Patches boto3.client() to return mocked clients that respond with
    predefined data instead of making real AWS API calls.
    """

    def __init__(self):
        self.original_client = None
        self.call_counts = defaultdict(lambda: defaultdict(int))
        self.mock_config = {}
        self.base_path = None

    def patch(self, mock_config: dict, base_path: Path):
        """Patch boto3.client() to return mocked clients."""
        self.mock_config = mock_config
        self.base_path = base_path

        # Save original
        self.original_client = boto3.client

        # Replace with mocked version
        boto3.client = self._create_mocked_client

    def unpatch(self):
        """Restore original boto3.client."""
        if self.original_client:
            boto3.client = self.original_client

    def _create_mocked_client(self, service_name, **kwargs):
        """Create mocked boto3 client for a service."""
        if service_name not in self.mock_config:
            # No mocks for this service - use real client
            return self.original_client(service_name, **kwargs)

        mock_client = MagicMock()
        service_mocks = self.mock_config[service_name]

        for operation, responses in service_mocks.items():
            # Resolve fixture files
            responses = self.resolve_fixture(responses, self.base_path)

            # Convert CamelCase to snake_case for method name
            method_name = self._to_snake_case(operation)

            # Create mock method
            def create_method(svc, op, resp):
                def method(**call_kwargs):
                    # Handle multiple responses (list)
                    if isinstance(resp, list):
                        call_num = self.call_counts[svc][op]
                        self.call_counts[svc][op] += 1
                        idx = min(call_num, len(resp) - 1)
                        return resp[idx].get('response', resp[idx])
                    else:
                        # Single response
                        return resp.get('response', resp)
                return method

            setattr(mock_client, method_name,
                   create_method(service_name, operation, responses))

        return mock_client

    def _to_snake_case(self, name: str) -> str:
        """Convert CamelCase to snake_case.

        Examples:
            GetMetricData -> get_metric_data
            ListBuckets -> list_buckets
        """
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
```

### 6. Local MCP Server Connection

**Critical Requirement:** Always test local MCP server code, NOT installed packages.

```python
# framework/mcp/client.py
from pathlib import Path
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from loguru import logger
import os

def connect_to_mcp_server(
    server_path: str,
    mock_file: str = None,
    verbose: bool = False,
):
    """Connect to LOCAL MCP server.

    Args:
        server_path: Path to MCP server.py (relative or absolute)
        mock_file: Optional path to JSON file with mocks
        verbose: Enable verbose logging

    Returns:
        MCP client connection context manager

    Raises:
        FileNotFoundError: If server file doesn't exist

    Examples:
        # Relative path
        connect_to_mcp_server(
            server_path='../../awslabs/cloudwatch_appsignals_mcp_server/server.py'
        )

        # Absolute path
        connect_to_mcp_server(
            server_path='/abs/path/to/server.py'
        )
    """

    # Resolve to absolute path
    local_server = Path(server_path).resolve()

    if not local_server.exists():
        raise FileNotFoundError(
            f"MCP server not found: {local_server}\n"
            f"Provided path: {server_path}"
        )

    logger.debug(f"Using MCP server: {local_server}")

    # Setup environment
    env = os.environ.copy()

    if not verbose:
        env['LOGURU_LEVEL'] = 'ERROR'

    # Add directory containing server to PYTHONPATH for imports
    server_dir = local_server.parent
    pythonpath = str(server_dir)
    if 'PYTHONPATH' in env:
        pythonpath = f"{pythonpath}:{env['PYTHONPATH']}"
    env['PYTHONPATH'] = pythonpath

    # Determine command
    if mock_file:
        # With mocks - use wrapper
        env['MCP_MOCK_FILE'] = str(Path(mock_file).resolve())
        env['MCP_SERVER_FILE'] = str(local_server)

        wrapper_file = Path(__file__).parent / 'mock_server_wrapper.py'

        server_params = StdioServerParameters(
            command='python',
            args=[str(wrapper_file)],
            env=env,
        )
    else:
        # No mocks - run server directly
        server_params = StdioServerParameters(
            command='python',
            args=[str(local_server)],
            env=env,
        )

    return stdio_client(server_params)
```

### 7. Mock Server Wrapper

```python
# framework/mcp/mock_server_wrapper.py
"""
Wrapper that patches libraries BEFORE starting MCP server.

This runs in the MCP server subprocess and applies mocks before
the server code executes.
"""
import os
import sys
import json
from pathlib import Path

def setup_mocks():
    """Setup all mocks before starting MCP server."""
    mock_file = os.environ.get('MCP_MOCK_FILE')
    if not mock_file:
        return

    # Load mock configuration
    with open(mock_file) as f:
        data = json.load(f)

    base_path = Path(data.get('base_path', Path.cwd()))
    mock_data = data['mocks']

    # Import mock registry
    from framework.mocking.base import MOCK_REGISTRY

    # Auto-discover and load all built-in handlers
    from framework.mocking.handlers import boto3_handler

    # Apply each mock type
    for mock_type, mock_config in mock_data.items():
        try:
            handler = MOCK_REGISTRY.create_handler(mock_type)
            handler.patch(mock_config, base_path)
            print(f"[Mock] Loaded {mock_type} mocks", file=sys.stderr)
        except ValueError as e:
            print(f"[Mock] Warning: {e}", file=sys.stderr)


if __name__ == '__main__':
    # Setup mocks FIRST (before importing server)
    setup_mocks()

    # Get the server file path
    server_file = os.environ.get('MCP_SERVER_FILE')

    if not server_file:
        print("Error: MCP_SERVER_FILE not set", file=sys.stderr)
        sys.exit(1)

    # Run the local server file directly
    with open(server_file) as f:
        code = compile(f.read(), server_file, 'exec')
        exec(code, {'__name__': '__main__', '__file__': server_file})
```

### 8. EvalRunner

```python
# framework/runner.py
import asyncio
import tempfile
import json
from pathlib import Path
from loguru import logger

class EvalRunner:
    """Orchestrates evaluation execution."""

    def __init__(
        self,
        tasks: list['Task'],
        server_path: str,
    ):
        """Initialize eval runner.

        Args:
            tasks: List of tasks to run
            server_path: Path to MCP server.py (required)

        Examples:
            # Relative path
            EvalRunner(
                TASKS,
                server_path='../../awslabs/cloudwatch_appsignals_mcp_server/server.py'
            )

            # Absolute path
            EvalRunner(
                TASKS,
                server_path='/absolute/path/to/server.py'
            )

        Raises:
            ValueError: If server_path not provided
        """
        if not server_path:
            raise ValueError("server_path is required")

        self.tasks = tasks
        self.server_path = server_path

    def run(self, task_id: str = None):
        """Run all tasks or specific task.

        Args:
            task_id: Optional task ID to run. If None, runs all tasks.
        """
        tasks = self.tasks
        if task_id:
            tasks = [t for t in tasks if t.id == task_id]
            if not tasks:
                logger.error(f"Task '{task_id}' not found")
                return

        asyncio.run(self._run_async(tasks))

    async def _run_async(self, tasks: list['Task']):
        """Run tasks asynchronously."""
        for task in tasks:
            await self._run_task(task)

    async def _run_task(self, task: 'Task'):
        """Run a single task."""
        logger.info(f"Running: {task.id}")

        # Get mocks
        mocks = task.get_mocks()

        # Serialize mocks to temp file if present
        mock_file = None
        if mocks:
            base_path = Path(__file__).parent.parent  # evals/

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump({
                    'base_path': str(base_path),
                    'mocks': mocks
                }, f, indent=2)
                mock_file = f.name

        try:
            # Connect to MCP server
            from .mcp.client import connect_to_mcp_server
            from mcp import ClientSession

            async with connect_to_mcp_server(
                server_path=self.server_path,
                mock_file=mock_file
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # Get prompts (always a list)
                    prompts = task.get_prompt()

                    # Run agent loop with multi-prompt support
                    from .agent import run_agent_loop
                    results = await run_agent_loop(
                        session=session,
                        prompts=prompts,  # Pass list of prompts
                        max_turns=task.max_turns,
                    )

                    # Create evaluation context
                    context = EvalContext(
                        task=task,
                        agent_results=results,
                        project_root=Path.cwd(),
                    )

                    # Run captors
                    captured_data = {}
                    for captor in task.get_captors():
                        captured_data[captor.output_key] = await captor.capture(context)

                    # Run validators
                    validation_results = {}
                    for validator in task.get_validators():
                        result = await validator.validate(captured_data)
                        validation_results[validator.output_metric] = result

                    # Compute metrics
                    from .metrics import compute_metrics
                    metrics = compute_metrics(results, task.expected_tools)

                    # Report
                    self._report(task, validation_results, metrics)

        finally:
            # Cleanup temp file
            if mock_file:
                Path(mock_file).unlink(missing_ok=True)

    def _report(self, task, validation_results, metrics):
        """Print results."""
        # Determine overall pass
        overall_pass = all(v.get('passed', False) for v in validation_results.values())

        status = "✅ PASSED" if overall_pass else "❌ FAILED"
        logger.info(f"\n{status} {task.id} ({metrics['duration']:.1f}s)")
        logger.info(f"  Hit rate: {metrics['hit_rate']:.0%}")
        logger.info(f"  Success rate: {metrics['success_rate']:.0%}")

        for metric_name, result in validation_results.items():
            if result.get('passed'):
                logger.info(f"  ✓ {metric_name}")
            else:
                logger.info(f"  ✗ {metric_name}")
                if 'reasoning' in result:
                    logger.info(f"    {result['reasoning']}")


class EvalContext:
    """Context passed to captors."""

    def __init__(self, task, agent_results, project_root):
        self.task = task
        self.agent_results = agent_results
        self.project_root = project_root
```

---

## Usage Examples

### Example 1: Enablement Eval (Code Modification)

```python
# evals/eval_enablement.py
from dataclasses import dataclass
from framework import Task, EvalRunner

@dataclass
class EnablementTask(Task):
    language: str
    framework: str
    platform: str
    iac_directory: str
    app_directory: str

    def get_prompt(self) -> list[str]:
        # Single prompt
        return [f"""Enable Application Signals for this {self.framework} app.

Language: {self.language}
Platform: {self.platform}

IaC: {self.iac_directory}
App: {self.app_directory}

Use get_enablement_guide tool to get instructions."""]

    @property
    def rubric(self) -> list[str]:
        return [
            "IaC code includes Application Signals instrumentation",
            "Application code has proper imports for ADOT",
        ]

    @property
    def expected_tools(self) -> list[str]:
        return ['get_enablement_guide']

    def get_validators(self):
        from framework.validators import LLMJudgeValidator, BuildValidator
        return [
            LLMJudgeValidator(rubric=self.rubric, input_from=['git_diff']),
            BuildValidator(command='npm run build', working_dir=self.app_directory),
        ]

    def get_mocks(self):
        # No mocks - uses real MCP tool
        return None


TASKS = [
    EnablementTask(
        id="ec2_python_flask",
        language="python",
        framework="flask",
        platform="ec2",
        iac_directory="iac/ec2-python-flask",
        app_directory="app/flask-app",
    ),
]

if __name__ == '__main__':
    runner = EvalRunner(
        TASKS,
        server_path='../../awslabs/cloudwatch_appsignals_mcp_server/server.py'
    )
    runner.run()
```

### Example 2: Cost Anomaly Eval (Data Interpretation with Mocks)

```python
# evals/eval_cost_anomalies.py
from dataclasses import dataclass
from framework import Task, EvalRunner

@dataclass
class CostAnomalyTask(Task):
    scenario: str
    expected_finding: str

    def get_prompt(self) -> list[str]:
        return [f"Analyze AWS costs. {self.scenario}"]

    @property
    def rubric(self) -> list[str]:
        return [
            f"Agent identified {self.expected_finding}",
            "Agent provided cost impact in dollars",
        ]

    @property
    def expected_tools(self) -> list[str]:
        return ['analyze_cost_anomalies']

    def get_captors(self):
        from framework.captors import ToolCallsCaptor, FinalResponseCaptor
        return [
            ToolCallsCaptor(),
            FinalResponseCaptor(),
        ]

    def get_validators(self):
        from framework.validators import LLMJudgeValidator
        return [
            LLMJudgeValidator(
                rubric=self.rubric,
                input_from=['final_response']
            )
        ]

    def get_mocks(self):
        return {
            'boto3': {
                'ce': {
                    'GetAnomalies': 'fixtures/ce/ec2_spike.json',
                    'GetCostAndUsage': {
                        'ResultsByTime': [
                            {'Total': {'UnblendedCost': {'Amount': '450.00'}}},
                            {'Total': {'UnblendedCost': {'Amount': '1650.50'}}}
                        ]
                    }
                },
                'cloudwatch': {
                    'GetMetricData': 'fixtures/cloudwatch/ec2_metrics.json'
                }
            }
        }


TASKS = [
    CostAnomalyTask(
        id="ec2_spike",
        scenario="EC2 costs increased from $450 to $1650",
        expected_finding="m5.2xlarge instance spike in us-east-1"
    ),
]

if __name__ == '__main__':
    runner = EvalRunner(
        TASKS,
        server_path='../../awslabs/cloudwatch_appsignals_mcp_server/server.py'
    )
    runner.run()
```

### Example 3: Multi-Prompt Root Cause Investigation

```python
# evals/eval_root_cause.py
from dataclasses import dataclass
from framework import Task, EvalRunner

@dataclass
class RootCauseTask(Task):
    scenario: str

    def get_prompt(self) -> list[str]:
        # Multiple prompts - sent sequentially
        return [
            "What services are experiencing issues?",
            "Investigate the database service specifically",
            "What's the root cause of the connection errors?"
        ]

    @property
    def rubric(self) -> list[str]:
        return [
            "Agent identified database as problematic",
            "Agent found connection pool exhaustion",
            "Agent suggested increasing pool size"
        ]

    @property
    def expected_tools(self) -> list[str]:
        return ['audit_services', 'get_metric_data']

    def get_mocks(self):
        return {
            'boto3': {
                'cloudwatch': {
                    # Multiple responses for repeated calls
                    'GetMetricData': [
                        {"MetricDataResults": [{"Values": [50, 52, 48]}]},  # 1st call
                        {"MetricDataResults": [{"Values": [195, 198, 200]}]}  # 2nd call
                    ]
                }
            }
        }


TASKS = [
    RootCauseTask(
        id="database_connection_pool",
        scenario="Connection timeouts"
    ),
]

if __name__ == '__main__':
    runner = EvalRunner(
        TASKS,
        server_path='../../awslabs/cloudwatch_appsignals_mcp_server/server.py'
    )
    runner.run()
```

---

## Implementation Plan

### Phase 1: Core Architecture (Week 1)

**Priority: Critical - Foundation for everything else**

#### Day 1-2: Base Classes

- [ ] `Task` base class in `framework/core.py`
  - `get_prompt()` returning `list[str]`
  - `rubric` property
  - `get_mocks()`, `get_captors()`, `get_validators()`
  - `expected_tools` property

- [ ] `Captor` base class in `framework/captors/base.py`
  - `output_key` property
  - `capture()` method

- [ ] `Validator` base class in `framework/validators/base.py`
  - `validate()` method
  - `output_metric` property

- [ ] `EvalContext` in `framework/runner.py`

#### Day 3-4: Built-in Captors

- [ ] `GitDiffCaptor` - captures git diff
- [ ] `ToolCallsCaptor` - captures tool usage
- [ ] `ConversationCaptor` - captures full conversation
- [ ] `FinalResponseCaptor` - captures agent's final answer
- [ ] `ToolResultsCaptor` - captures tool outputs

#### Day 5-6: Built-in Validators

- [ ] `LLMJudgeValidator` - LLM-as-judge with rubric
- [ ] `BuildValidator` - runs build commands
- [ ] Create specialized prompts in `validation_prompts.py`
  - Code validation prompt
  - Data interpretation prompt
  - Workflow validation prompt

#### Day 7: Mock System Foundation

- [ ] `MockHandler` base class with `resolve_fixture()`
- [ ] `MockHandlerRegistry` with self-documentation
- [ ] `Boto3MockHandler` with fixture resolution and sequential responses
- [ ] `mock_server_wrapper.py` to apply patches in subprocess

### Phase 2: Integration & MCP (Week 2)

**Priority: High - Make it work end-to-end**

#### Day 8-9: MCP Client Updates

- [ ] Modify `connect_to_mcp_server()` to accept `server_path`
- [ ] Use local file path (not module import)
- [ ] Add mock file support with temp file handling
- [ ] Add logging to show which server file is used
- [ ] Test that local changes are picked up

#### Day 10-12: EvalRunner Implementation

- [ ] Task orchestration
- [ ] Multi-prompt support in agent loop
- [ ] Captor execution
- [ ] Validator execution
- [ ] Mock serialization to temp file
- [ ] Result reporting with pretty formatting

#### Day 13-14: Metrics & Cleanup

- [ ] Update `metrics.py` for hit rate/success rate
  - Fix error code handling (-1 vs actual codes)
  - Add explicit length check for hit rate
- [ ] Improve subprocess cleanup with proper status checking
- [ ] Add timestamp formatting to all logger calls

### Phase 3: Migration & Polish (Week 3)

**Priority: Medium - Clean up and document**

#### Day 15-16: Refactor Existing Eval

- [ ] Move `ENABLEMENT_TASK_PROMPT` to `EnablementTask.get_prompt()`
- [ ] Refactor `eval_enablement.py` to use new Task class
- [ ] Test migrated eval works correctly
- [ ] Remove old constants.py

#### Day 17-18: CLI & UX Improvements

- [ ] Add `--list-tasks` CLI option
- [ ] Add `--list-mocks` CLI option to show available mock types
- [ ] Add `--debug` flag to show server path and other debug info
- [ ] Improve error messages

#### Day 19-20: Documentation & Helpers

- [ ] `capture_boto3_response()` helper function
- [ ] `docs/MOCK_REFERENCE.md` - Quick reference
- [ ] `docs/MOCK_HANDLER_TEMPLATE.md` - Extension guide
- [ ] Update README with new architecture
- [ ] Add inline code examples

#### Day 21: Testing & Validation

- [ ] Test with existing enablement eval
- [ ] Create example eval for data interpretation
- [ ] Create example eval for multi-prompt workflow
- [ ] Verify local MCP server detection works
- [ ] Test mock system with various scenarios

### Future Enhancements (Post-Refactor)

**Priority: Low - Track for later**

- [ ] **Security**: Add prompt injection defenses to LLM judge
- [ ] **Additional Handlers**: RequestsMockHandler, DatabaseMockHandler
- [ ] **Advanced Prompts**: `get_follow_ups()` for conditional prompts
- [ ] **Advanced Prompts**: `get_conversation()` for structured flows
- [ ] **Performance**: Parallel task execution
- [ ] **UX**: Result caching
- [ ] **Reporting**: HTML report generation

---

## Migration Guide

### For Existing Eval Authors

**Old way (current):**
```python
# evals/eval_enablement.py
from framework import run_agent_loop, validate_with_llm
from framework.constants import ENABLEMENT_TASK_PROMPT

# Manual orchestration
results = await run_agent_loop(...)
validation = await validate_with_llm(...)
# No mocking support
```

**New way:**
```python
# evals/eval_enablement.py
from framework import Task, EvalRunner
from dataclasses import dataclass

@dataclass
class EnablementTask(Task):
    def get_prompt(self) -> list[str]:
        return ["..."]  # Prompt here

    @property
    def rubric(self) -> list[str]:
        return [...]

    def get_mocks(self):
        return {...}  # Optional

# Framework handles everything
runner = EvalRunner(TASKS, server_path='...')
runner.run()
```

### Breaking Changes

1. **Task definition** - Must subclass `Task`
2. **Prompts** - Always return `list[str]`, move from constants to task
3. **Validation** - Use validators instead of direct function calls
4. **Metrics** - Automatically computed
5. **Server path** - Must be explicitly provided to EvalRunner

### Step-by-Step Migration

1. Create new Task class extending `Task`
2. Move prompt from constants to `get_prompt()`
3. Define rubric as property
4. Optionally add mocks in `get_mocks()`
5. Create EvalRunner with server path
6. Remove old constants and manual orchestration code

---

## Success Criteria

### Technical

- ✅ All captors/validators are reusable across eval types
- ✅ Mocking works with any boto3 service
- ✅ Local MCP server changes are always tested
- ✅ No MCP-specific code in generic framework
- ✅ Easy to add new captor/validator types
- ✅ Multi-prompt support works seamlessly
- ✅ Server path is explicit and configurable

### User Experience

- ✅ New eval takes < 30 lines of code
- ✅ Clear error messages when things go wrong
- ✅ `--list-mocks` shows available mock types
- ✅ Documentation is clear and comprehensive
- ✅ Mocking is simple (just return a dict)
- ✅ No ambiguity about which server is being tested

### PR Review

- ✅ Addresses all feedback from thpierce
- ✅ Passes code quality checks
- ✅ No security warnings from subprocess usage
- ✅ Clean separation of concerns

---

## Questions & Answers

### Q: Why separate captors and validators?

**A:** Different eval types need different combinations:
- Code modification → capture git diff, validate with LLM + build
- Data interpretation → capture tool results + response, validate with LLM
- Workflow → capture tool sequence, validate order

Separation enables composition and reuse.

### Q: Why dict-based mocking instead of classes?

**A:** Simpler for users:
- Just copy-paste AWS API response structure
- No need to learn MockClient API
- Framework handles complexity behind the scenes
- Matches reviewer's request for "simple code"

### Q: Why test local MCP server instead of installed package?

**A:** Developer workflow requirement:
1. Make local code change
2. Run eval
3. See if change breaks anything
4. Fix and repeat

Testing installed package defeats this purpose.

### Q: Why always return `list[str]` from `get_prompt()`?

**A:** Consistency and simplicity:
- No type union complexity (`str | list[str]`)
- Framework code simpler (no type checking)
- Clear intent - even single prompt is explicit: `["prompt"]`
- Easy to extend to multi-prompt later

### Q: Why require server_path explicitly?

**A:** Avoid ambiguity:
- Makes it crystal clear which server is being tested
- No magic auto-detection that might fail
- Supports any server location/structure
- Reviewer feedback: want to ensure testing local code

### Q: Can I use the old validation.py functions?

**A:** No, they'll be removed. Use validators:
```python
# Old
result = await validate_with_llm(bedrock_client, rubric, git_diff)

# New
validator = LLMJudgeValidator(rubric, input_from=['git_diff'])
result = await validator.validate(captured_data)
```

### Q: How do I add support for a new library (not boto3)?

**A:** Create a new MockHandler:
1. Extend `MockHandler` base class
2. Implement `patch()` and `unpatch()`
3. Register with `MOCK_REGISTRY`
4. See `docs/MOCK_HANDLER_TEMPLATE.md` for guide

---

## Risks & Mitigations

### Risk 1: Breaking Existing Evals

**Impact:** High
**Probability:** Certain

**Mitigation:**
- Migrate `eval_enablement.py` as part of this work
- Document migration guide clearly
- Provide working examples for all common patterns

### Risk 2: Mock System Too Complex

**Impact:** Medium
**Probability:** Low

**Mitigation:**
- Start with boto3 only (covers 90% of use cases)
- Provide clear examples and helper function
- Add `--list-mocks` to show usage
- Create `capture_boto3_response()` to simplify mock creation

### Risk 3: Local Server Detection Issues

**Impact:** High
**Probability:** Low

**Mitigation:**
- Require explicit `server_path` parameter
- Clear error messages showing full path
- Add `--debug` flag to verify server location
- Log server path on every run

### Risk 4: Multi-Prompt Complexity

**Impact:** Low
**Probability:** Medium

**Mitigation:**
- Start with simple sequential prompts
- Defer conditional/dynamic prompts to future
- Provide clear examples
- Test with multiple scenarios

---

## Appendix: Quick Reference

### Minimal Task Example

```python
from dataclasses import dataclass
from framework import Task, EvalRunner

@dataclass
class MyTask(Task):
    def get_prompt(self) -> list[str]:
        return ["Do something"]

    @property
    def rubric(self) -> list[str]:
        return ["It worked"]

runner = EvalRunner([MyTask(id='test')], server_path='path/to/server.py')
runner.run()
```

### Custom Captor Example

```python
from framework.captors import Captor

class MetricsCaptor(Captor):
    @property
    def output_key(self) -> str:
        return 'metrics'

    async def capture(self, context):
        return {
            'duration': context.agent_results['duration'],
            'tool_count': len(context.agent_results['tool_calls'])
        }
```

### Custom Validator Example

```python
from framework.validators import Validator

class ResponseLengthValidator(Validator):
    def __init__(self, min_length=100):
        super().__init__()
        self.min_length = min_length

    async def validate(self, captured_data):
        response = captured_data.get('final_response', '')
        passed = len(response) >= self.min_length
        return {
            'passed': passed,
            'details': {'length': len(response), 'min': self.min_length}
        }
```

### Capture Real AWS Response

```python
from framework.mocking.helpers import capture_boto3_response

# Make real API call and save
capture_boto3_response(
    service='ce',
    operation='get_anomalies',
    DateInterval={'StartDate': '2024-01-01', 'EndDate': '2024-01-31'}
)
# Output: ✓ Saved to fixtures/ce/get_anomalies.json

# Use in task
def get_mocks(self):
    return {
        'boto3': {
            'ce': {
                'GetAnomalies': 'fixtures/ce/get_anomalies.json'
            }
        }
    }
```

### Multi-Prompt Example

```python
def get_prompt(self) -> list[str]:
    # Single prompt
    return ["Investigate the issue"]

    # OR multi-step
    return [
        "What services have issues?",
        "Check the database",
        "What's the root cause?"
    ]
```

---

**End of Refactor Plan**

Version: 1.0
Last Updated: 2025-01-15
Author: Architecture discussion with yiyuanh
Related PR: #1618
