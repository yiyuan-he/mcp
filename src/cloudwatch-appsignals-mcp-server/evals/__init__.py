"""MCP Evaluation Framework.

A framework for evaluating MCP tool performance using multi-turn agent interactions
with LLM-as-a-judge validation.
"""

from pathlib import Path

# TEMPORARY: MCP project root calculation
# This is nested deeply because eval framework currently lives in:
# mcp/src/cloudwatch-appsignals-mcp-server/evals/
# Once eval framework moves to a higher-level directory, this can be simplified
# Example: evals/__init__.py -> evals/ -> cloudwatch-appsignals-mcp-server/ -> src/ -> mcp/
MCP_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
