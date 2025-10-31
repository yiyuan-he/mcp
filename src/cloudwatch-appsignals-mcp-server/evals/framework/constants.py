"""Configuration constants for MCP tool evaluation framework.

Centralized location for all configurable values.
"""

# AWS Bedrock configuration
DEFAULT_MODEL_ID = 'us.anthropic.claude-sonnet-4-20250514-v1:0'
DEFAULT_AWS_REGION = 'us-east-1'

# Agent configuration
DEFAULT_MAX_TURNS = 20
DEFAULT_TEMPERATURE = 0.0

# Specialized validation prompts for different eval types

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
