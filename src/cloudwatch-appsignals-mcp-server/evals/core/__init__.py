"""Generic evaluation framework for MCP tools.

This framework provides reusable components for evaluating MCP tools:
- Task: Base class for defining evaluation tasks with prompts, rubrics, and mocks
- Captors: Extract specific outputs (git diff, tool calls, responses)
- Validators: Evaluate captured data against rubrics (LLM judge, build validation)
- Mocking: Mock external dependencies (boto3, etc.) in MCP server subprocess
- EvalRunner: Orchestrate task execution and validation
- MetricsTracker: Track tool usage, success rates, hit rates
"""

# Core abstractions
from .task import Task
from .captor import (
    Captor,
    GitDiffCaptor,
    ToolCallsCaptor,
    ConversationCaptor,
    FinalResponseCaptor,
    ToolResultsCaptor,
)
from .validator import Validator, LLMJudgeValidator, BuildValidator
from .llm_provider import LLMProvider, BedrockLLMProvider
from .process_executor import ProcessExecutor, SubprocessExecutor
from .fixture_resolver import FixtureResolver
from .eval_runner import EvalRunner
from .eval_runner_result import EvalRunnerResult

# Mocking system
from .mocking import MockHandler, Boto3MockHandler, MockHandlerRegistry, get_registry

# Lower-level utilities
from .agent import execute_tool, run_agent_loop
from .file_tools import get_file_tools
from .mcp_client import connect_to_mcp_server, convert_mcp_tools_to_bedrock
from .metrics_tracker import MetricsTracker


__all__ = [
    # Core classes
    'Task',
    'Captor',
    'Validator',
    'EvalRunner',
    'EvalRunnerResult',
    # Built-in captors
    'GitDiffCaptor',
    'ToolCallsCaptor',
    'ConversationCaptor',
    'FinalResponseCaptor',
    'ToolResultsCaptor',
    # Built-in validators
    'LLMJudgeValidator',
    'BuildValidator',
    # LLM providers
    'LLMProvider',
    'BedrockLLMProvider',
    # Process executors
    'ProcessExecutor',
    'SubprocessExecutor',
    # Fixture resolution
    'FixtureResolver',
    # Mocking
    'MockHandler',
    'Boto3MockHandler',
    'MockHandlerRegistry',
    'get_registry',
    # Utilities
    'MetricsTracker',
    'connect_to_mcp_server',
    'convert_mcp_tools_to_bedrock',
    'get_file_tools',
    'execute_tool',
    'run_agent_loop',
]
