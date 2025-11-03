"""Configuration constants for MCP tool evaluation framework.

Centralized location for all configurable values.

Environment variable overrides:
- MCP_EVAL_MODEL_ID: Override default Bedrock model ID
- MCP_EVAL_AWS_REGION: Override default AWS region
- MCP_EVAL_MAX_TURNS: Override default max conversation turns
- MCP_EVAL_TEMPERATURE: Override default model temperature
"""

import os


# Fallback values (used when environment variables are not set)
_FALLBACK_MODEL_ID = 'us.anthropic.claude-sonnet-4-20250514-v1:0'
_FALLBACK_AWS_REGION = 'us-east-1'
_FALLBACK_MAX_TURNS = 20
_FALLBACK_TEMPERATURE = 0.0

# AWS Bedrock configuration (configurable via environment variables)
DEFAULT_MODEL_ID = os.environ.get('MCP_EVAL_MODEL_ID', _FALLBACK_MODEL_ID)
DEFAULT_AWS_REGION = os.environ.get('MCP_EVAL_AWS_REGION', _FALLBACK_AWS_REGION)

# Agent configuration (configurable via environment variables)
DEFAULT_MAX_TURNS = int(os.environ.get('MCP_EVAL_MAX_TURNS', str(_FALLBACK_MAX_TURNS)))
DEFAULT_TEMPERATURE = float(os.environ.get('MCP_EVAL_TEMPERATURE', str(_FALLBACK_TEMPERATURE)))

# LLM-as-a-Judge Validation Prompts
# Best practices: https://www.evidentlyai.com/llm-guide/llm-as-a-judge

CODE_MODIFICATION_VALIDATION_PROMPT = """You are evaluating code changes for a software modification task.

**Validation Rubric:**
{rubric_items}

{captured_data}

Instructions:
For each criterion in the rubric, evaluate whether it is satisfied by the changes and captured data.

Respond in this EXACT format:
1. [PASS/FAIL] Brief reasoning (1 sentence)
2. [PASS/FAIL] Brief reasoning (1 sentence)
... (continue for all {num_criteria} criteria)

Be strict but fair. Only mark as PASS if the criterion is clearly met."""

DATA_INTERPRETATION_VALIDATION_PROMPT = """You are evaluating an agent's data interpretation and analysis task.

**Validation Rubric:**
{rubric_items}

{captured_data}

Instructions:
For each criterion in the rubric, evaluate whether the agent's response correctly addresses it.

Respond in this EXACT format:
1. [PASS/FAIL] Brief reasoning (1 sentence)
2. [PASS/FAIL] Brief reasoning (1 sentence)
... (continue for all {num_criteria} criteria)

Be strict but fair. Only mark as PASS if the agent's answer is accurate and complete."""

WORKFLOW_VALIDATION_PROMPT = """You are evaluating whether an agent followed the correct workflow and tool usage.

**Validation Rubric:**
{rubric_items}

{captured_data}

Instructions:
For each criterion in the rubric, evaluate whether the agent's tool usage and workflow meets it.

Respond in this EXACT format:
1. [PASS/FAIL] Brief reasoning (1 sentence)
2. [PASS/FAIL] Brief reasoning (1 sentence)
... (continue for all {num_criteria} criteria)

Be strict but fair. Only mark as PASS if the criterion is clearly met."""
