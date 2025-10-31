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
from .runner import EvalRunner

# Mocking system
from .mocking import MockHandler, Boto3MockHandler, MockHandlerRegistry, get_registry

# Lower-level utilities
from .agent import execute_tool, run_agent_loop
from .file_tools import get_file_tools
from .mcp_client import connect_to_mcp_server, convert_mcp_tools_to_bedrock
from .metrics import MetricsTracker
from .validation import run_build_validation, validate_with_llm


__all__ = [
    # Core classes
    'Task',
    'Captor',
    'Validator',
    'EvalRunner',
    # Built-in captors
    'GitDiffCaptor',
    'ToolCallsCaptor',
    'ConversationCaptor',
    'FinalResponseCaptor',
    'ToolResultsCaptor',
    # Built-in validators
    'LLMJudgeValidator',
    'BuildValidator',
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
    'validate_with_llm',
    'run_build_validation',
]
