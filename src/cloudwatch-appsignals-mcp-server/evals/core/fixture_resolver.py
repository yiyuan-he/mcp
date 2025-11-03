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

"""Fixture path resolution utility for evaluation framework.

Handles conversion of relative fixture file paths to absolute paths
in mock configurations.
"""

from pathlib import Path
from typing import Any, Dict


class FixtureResolver:
    """Resolves fixture file paths in mock configurations.

    Converts relative fixture paths to absolute paths based on a fixtures directory.
    This enables mock configurations to use relative paths like 'services.json'
    which get resolved to absolute paths like '/path/to/fixtures/services.json'.
    """

    @staticmethod
    def resolve_mock_config(
        mock_config: Dict[str, Any], fixtures_dir: Path
    ) -> Dict[str, Any]:
        """Resolve all fixture paths in a mock configuration.

        Args:
            mock_config: Mock configuration dictionary with relative fixture paths
            fixtures_dir: Base directory for resolving fixture file paths

        Returns:
            Mock configuration with all relative paths resolved to absolute paths

        Example:
            mock_config = {
                'boto3': {
                    'application-signals': {
                        'list_services': [
                            {'request': {}, 'response': 'services.json'}
                        ]
                    }
                }
            }
            resolved = FixtureResolver.resolve_mock_config(
                mock_config,
                Path('/fixtures')
            )
            # Result: 'response' becomes '/fixtures/services.json'
        """
        return FixtureResolver._resolve_fixture_paths(mock_config, fixtures_dir)

    @staticmethod
    def has_fixture_references(mock_config: Dict[str, Any]) -> bool:
        """Check if mock configuration contains relative fixture file references.

        Args:
            mock_config: Mock configuration dictionary

        Returns:
            True if any value looks like a relative fixture file path

        Example:
            has_refs = FixtureResolver.has_fixture_references({
                'boto3': {
                    'cloudwatch': {
                        'get_metric_data': [
                            {'request': {}, 'response': 'metrics.json'}
                        ]
                    }
                }
            })
            # Returns: True
        """
        for key, value in mock_config.items():
            if isinstance(value, dict):
                if FixtureResolver.has_fixture_references(value):
                    return True
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and 'response' in item:
                        response = item['response']
                        if isinstance(response, str) and (
                            response.endswith('.json') or response.endswith('.txt')
                        ):
                            # Check if it looks like a relative path (not absolute)
                            if not Path(response).is_absolute():
                                return True
            elif isinstance(value, str) and (value.endswith('.json') or value.endswith('.txt')):
                # Check if it looks like a relative path (not absolute)
                if not Path(value).is_absolute():
                    return True
        return False

    @staticmethod
    def _resolve_fixture_paths(
        mock_config: Dict[str, Any], fixtures_dir: Path
    ) -> Dict[str, Any]:
        """Recursively resolve fixture file paths to absolute paths.

        Args:
            mock_config: Mock configuration dictionary
            fixtures_dir: Base directory for fixture files

        Returns:
            Mock configuration with resolved paths
        """
        resolved = {}
        for key, value in mock_config.items():
            if isinstance(value, dict):
                # Recursively resolve nested dictionaries
                resolved[key] = FixtureResolver._resolve_fixture_paths(value, fixtures_dir)
            elif isinstance(value, list):
                # Lists should contain request/response pairs
                resolved[key] = [
                    FixtureResolver._resolve_request_response_pair(item, fixtures_dir)
                    for item in value
                ]
            else:
                # Pass through other values
                resolved[key] = value
        return resolved

    @staticmethod
    def _resolve_request_response_pair(
        pair: Dict[str, Any], fixtures_dir: Path
    ) -> Dict[str, Any]:
        """Resolve a request/response pair.

        Args:
            pair: Dict with 'request' and 'response' keys
            fixtures_dir: Base directory for fixture files

        Returns:
            Resolved pair with absolute response path

        Raises:
            ValueError: If pair doesn't have expected structure
        """
        if not isinstance(pair, dict) or 'request' not in pair or 'response' not in pair:
            raise ValueError(
                f"Expected request/response pair dict with 'request' and 'response' keys, got: {pair}"
            )

        response = pair['response']
        # Resolve response path if it's a string fixture reference
        if isinstance(response, str) and (response.endswith('.json') or response.endswith('.txt')):
            response = str(fixtures_dir / response)

        return {'request': pair['request'], 'response': response}
