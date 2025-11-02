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

import json
import os
import sys
import tempfile
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from pathlib import Path
from typing import Any, Dict, List, Optional


def connect_to_mcp_server(
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

    Returns:
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

    # Determine module path and working directory
    # For server.py with relative imports, we need to run as module
    # E.g., /path/to/awslabs/cloudwatch_appsignals_mcp_server/server.py
    #       -> module: awslabs.cloudwatch_appsignals_mcp_server.server
    #       -> cwd: /path/to (parent of awslabs)

    # Find the parent directory containing the package
    server_dir = server_file.parent
    package_name = server_dir.name  # e.g., cloudwatch_appsignals_mcp_server
    namespace_dir = server_dir.parent  # e.g., awslabs
    namespace_name = namespace_dir.name  # e.g., awslabs
    working_dir = namespace_dir.parent  # e.g., /path/to

    # Construct module path
    module_path = f'{namespace_name}.{package_name}.server'

    env = os.environ.copy()
    if not verbose:
        env['LOGURU_LEVEL'] = 'ERROR'

    # If mocks provided, write to temp file and use wrapper
    if mock_config:
        # Create temp file for mock config
        # Note: We don't delete this file immediately because the subprocess needs it.
        # It will be cleaned up by the OS temp directory cleanup.
        mock_fd, mock_file_path = tempfile.mkstemp(suffix='.json', prefix='mcp_mocks_')
        with os.fdopen(mock_fd, 'w') as f:
            json.dump(mock_config, f)

        # Set environment variable for wrapper to find mocks
        env['MCP_EVAL_MOCK_FILE'] = mock_file_path

        # Use wrapper to start server with mocks
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

        return stdio_client(server_params)
    else:
        # Direct connection without mocks - run as module
        # Use sys.executable to ensure we use the same Python interpreter (with venv)
        server_params = StdioServerParameters(
            command=sys.executable,
            args=['-m', module_path],
            env=env,
            cwd=str(working_dir),
        )
        return stdio_client(server_params)


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
