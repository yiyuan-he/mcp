# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""MCP client utilities.

Provides connection and tool conversion utilities for MCP servers.
"""

import contextlib
import json
import os
import sys
import tempfile
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from pathlib import Path
from typing import Any, Dict, List, Optional


@contextlib.asynccontextmanager
async def connect_to_mcp_server(
    server_path: str,
    verbose: bool = False,
    mock_config: Optional[Dict[str, Any]] = None,
):
    """Connect to an MCP server via stdio.

    Connects to a local MCP server file, optionally applying mocks
    to external dependencies (boto3, etc.) in the server subprocess.

    Args:
        server_path: Path to MCP server.py file (e.g., '../../src/server.py')
        verbose: Enable verbose logging from server
        mock_config: Optional mock configuration dictionary

    Yields:
        Context manager from stdio_client for MCP connection

    Example:
        # Without mocks
        async with connect_to_mcp_server('../../src/server.py') as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

        # With mocks
        mocks = {
            'boto3': {
                'cloudwatch': {
                    'GetMetricData': {'MetricDataResults': [...]}
                }
            }
        }
        async with connect_to_mcp_server('../../src/server.py', mock_config=mocks) as (read, write):
            ...
    """
    if not server_path:
        raise ValueError('server_path is required')

    # Resolve server path to absolute
    server_file = Path(server_path).resolve()
    if not server_file.exists():
        raise FileNotFoundError(f'MCP server not found: {server_path}')

    # Determine working directory for the server
    # For server.py with relative imports, we need to run from the correct directory
    # E.g., /path/to/awslabs/cloudwatch_appsignals_mcp_server/server.py
    #       -> cwd: /path/to (parent of awslabs)
    server_dir = server_file.parent
    namespace_dir = server_dir.parent
    working_dir = namespace_dir.parent

    env = os.environ.copy()
    if not verbose:
        env['LOGURU_LEVEL'] = 'ERROR'
        env['MCP_CLOUDWATCH_APPSIGNALS_LOG_LEVEL'] = 'WARNING'

    # Track temp file for cleanup
    mock_file_path = None

    try:
        # Always use wrapper for consistent logging configuration
        # If mocks provided, write to temp file
        if mock_config:
            # Create temp file for mock config
            mock_fd, mock_file_path = tempfile.mkstemp(suffix='.json', prefix='mcp_mocks_')
            with os.fdopen(mock_fd, 'w') as f:
                json.dump(mock_config, f)

            # Set environment variable for wrapper to find mocks
            env['MCP_EVAL_MOCK_FILE'] = mock_file_path

        # Use wrapper to start server (handles both mocked and non-mocked cases)
        # Run wrapper as a module so relative imports work
        # cwd must be where 'evals' package can be imported from
        from evals import MCP_PROJECT_ROOT

        mcp_server_root = MCP_PROJECT_ROOT / 'src' / 'cloudwatch-appsignals-mcp-server'

        # Use sys.executable to ensure we use the same Python interpreter (with venv)
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[
                '-m',
                'evals.core.mock_server_wrapper',
                str(server_file),
                '--server-cwd',
                str(working_dir),
            ],
            env=env,
            cwd=str(mcp_server_root),
        )

        # Yield the stdio_client context manager
        async with stdio_client(server_params) as client:
            yield client

    finally:
        # Clean up temp file after server subprocess has finished
        if mock_file_path and os.path.exists(mock_file_path):
            try:
                os.unlink(mock_file_path)
            except OSError:
                # Best effort cleanup - don't fail if we can't delete
                pass


def convert_mcp_tools_to_bedrock(mcp_tools) -> List[Dict[str, Any]]:
    """Convert MCP tool format to Bedrock tool format.

    Args:
        mcp_tools: List of MCP tool definitions

    Returns:
        List of Bedrock-formatted tool specifications
    """
    bedrock_tools = []

    for tool in mcp_tools:
        bedrock_tool = {
            'toolSpec': {
                'name': tool.name,
                'description': tool.description or '',
                'inputSchema': {'json': tool.inputSchema},
            }
        }
        bedrock_tools.append(bedrock_tool)

    return bedrock_tools
