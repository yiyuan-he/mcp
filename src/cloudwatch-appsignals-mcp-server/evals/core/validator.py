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

"""Validators for evaluating agent outputs.

Validators take captured data and determine if the task
was completed successfully.
"""

import subprocess
import time
from .constants import DEFAULT_MODEL_ID, DEFAULT_TEMPERATURE
from abc import ABC, abstractmethod
from loguru import logger
from pathlib import Path
from typing import Any, Dict, List


class Validator(ABC):
    """Base class for output validation.

    Validators evaluate captured data against task criteria.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Return the name of this validator for display purposes."""
        pass

    @abstractmethod
    async def validate(
        self,
        captured_data: Dict[str, Any],
        rubric: List[str],
        bedrock_client: Any = None,
    ) -> Dict[str, Any]:
        """Validate captured data against rubric.

        Args:
            captured_data: Data captured by captors
            rubric: Validation criteria
            bedrock_client: Boto3 Bedrock client (for LLM validators)

        Returns:
            Dictionary with validation results including:
            - validator_name: str (name of this validator)
            - overall_pass: bool
            - criteria_results: List[dict] with per-criterion results
            - Additional validator-specific data
        """
        pass


class LLMJudgeValidator(Validator):
    """LLM-as-judge validator using Bedrock.

    Uses an LLM to evaluate captured data against validation rubric.
    """

    def __init__(self, validation_prompt_template: str):
        """Initialize LLM judge validator.

        Args:
            validation_prompt_template: Template string for LLM judge prompt.
                Should have placeholders for: rubric_items, captured_data, num_criteria
        """
        self.validation_prompt_template = validation_prompt_template

    def get_name(self) -> str:
        """Return validator name."""
        return 'LLM Judge'

    async def validate(
        self,
        captured_data: Dict[str, Any],
        rubric: List[str],
        bedrock_client: Any = None,
    ) -> Dict[str, Any]:
        """Validate using LLM as judge.

        Args:
            captured_data: Data captured by captors
            rubric: Validation criteria
            bedrock_client: Boto3 Bedrock Runtime client (required)

        Returns:
            Dictionary with validation results
        """
        if not bedrock_client:
            raise ValueError('bedrock_client is required for LLMJudgeValidator')

        logger.info('Running LLM-as-judge validation...')

        # Format rubric
        rubric_items = '\n'.join([f'{i + 1}. {criterion}' for i, criterion in enumerate(rubric)])

        # Format captured data for prompt
        captured_str = self._format_captured_data(captured_data)

        # Build prompt
        prompt = self.validation_prompt_template.format(
            rubric_items=rubric_items,
            captured_data=captured_str,
            num_criteria=len(rubric),
        )

        try:
            start = time.time()

            response = bedrock_client.converse(
                modelId=DEFAULT_MODEL_ID,
                messages=[{'role': 'user', 'content': [{'text': prompt}]}],
                inferenceConfig={'temperature': DEFAULT_TEMPERATURE},
            )

            elapsed = time.time() - start
            logger.debug(f'LLM validation took {elapsed:.2f}s')

            response_text = response['output']['message']['content'][0]['text']

            # Parse response
            criteria_results = self._parse_llm_response(response_text, rubric)
            overall_pass = all(r['status'] == 'PASS' for r in criteria_results)

            return {
                'validator_name': self.get_name(),
                'overall_pass': overall_pass,
                'criteria_results': criteria_results,
                'raw_response': response_text,
            }
        except Exception as e:
            logger.error(f'LLM validation failed: {e}')
            return {
                'validator_name': self.get_name(),
                'overall_pass': False,
                'error': f'Validation error: {str(e)}',
                'criteria_results': [],
            }

    def _format_captured_data(self, captured_data: Dict[str, Any]) -> str:
        """Format captured data for inclusion in prompt."""
        sections = []

        # Git diff
        if 'git_diff' in captured_data and captured_data['git_diff']:
            sections.append(f'**Git Diff:**\n```\n{captured_data["git_diff"]}\n```')

        # Build result
        if 'build_result' in captured_data:
            build = captured_data['build_result']
            if build.get('success'):
                sections.append('**Build Validation:**\n✓ Build succeeded (exit code 0)')
            else:
                stderr_preview = build.get('stderr', '')[:500]
                exit_code = build.get('exit_code', 'unknown')
                sections.append(
                    f'**Build Validation:**\n✗ Build FAILED (exit code {exit_code})\n\nBuild errors:\n{stderr_preview}'
                )

        # Final response
        if 'final_response' in captured_data:
            sections.append(f'**Agent Response:**\n{captured_data["final_response"]}')

        # Tool calls
        if 'tool_calls' in captured_data:
            tool_names = [t['name'] for t in captured_data['tool_calls']]
            sections.append(f'**Tools Called:** {", ".join(tool_names)}')

        return '\n\n'.join(sections)

    def _parse_llm_response(self, response_text: str, rubric: List[str]) -> List[Dict[str, Any]]:
        """Parse LLM response into structured criteria results."""
        criteria_results = []

        for line in response_text.strip().split('\n'):
            if not line.strip():
                continue

            if '[PASS]' in line.upper():
                status = 'PASS'
                reasoning = line.split('[PASS]', 1)[1].strip() if '[PASS]' in line else line
            elif '[FAIL]' in line.upper():
                status = 'FAIL'
                reasoning = line.split('[FAIL]', 1)[1].strip() if '[FAIL]' in line else line
            else:
                continue

            if len(criteria_results) < len(rubric):
                criteria_results.append(
                    {
                        'criterion': rubric[len(criteria_results)],
                        'status': status,
                        'reasoning': reasoning,
                    }
                )

        return criteria_results


class BuildValidator(Validator):
    """Validator that runs build commands.

    Executes a build command and validates based on exit code.
    """

    def __init__(
        self,
        command: str,
        working_dir: Path,
        timeout: int = 120,
    ):
        """Initialize build validator.

        Args:
            command: Build command to execute (e.g., 'npm install && npm run build')
            working_dir: Directory to run command in
            timeout: Command timeout in seconds
        """
        self.command = command
        self.working_dir = working_dir
        self.timeout = timeout

    def get_name(self) -> str:
        """Return validator name."""
        return 'Build'

    async def validate(
        self,
        captured_data: Dict[str, Any],
        rubric: List[str],
        bedrock_client: Any = None,
    ) -> Dict[str, Any]:
        """Validate by running build command.

        Args:
            captured_data: Captured data (unused)
            rubric: Validation criteria (unused)
            bedrock_client: Bedrock client (unused)

        Returns:
            Dictionary with build validation results
        """
        # Run build command
        logger.info(f'Running build command: {self.command}')
        try:
            build_result = subprocess.run(
                self.command,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=True,
            )

            result = {
                'exit_code': build_result.returncode,
                'stdout': build_result.stdout,
                'stderr': build_result.stderr,
                'success': build_result.returncode == 0,
            }

            if result['success']:
                logger.info('✓ Build succeeded')
                return {
                    'validator_name': self.get_name(),
                    'overall_pass': True,
                    'criteria_results': [
                        {
                            'criterion': 'Build succeeds',
                            'status': 'PASS',
                            'reasoning': 'Build completed with exit code 0',
                        }
                    ],
                    'build_result': result,
                }
            else:
                logger.error(f'✗ Build failed with exit code {build_result.returncode}')
                return {
                    'validator_name': self.get_name(),
                    'overall_pass': False,
                    'criteria_results': [
                        {
                            'criterion': 'Build succeeds',
                            'status': 'FAIL',
                            'reasoning': f'Build failed with exit code {build_result.returncode}',
                        }
                    ],
                    'build_result': result,
                }
        except Exception as e:
            logger.error(f'Build validation error: {e}')
            return {
                'validator_name': self.get_name(),
                'overall_pass': False,
                'error': str(e),
                'criteria_results': [
                    {
                        'criterion': 'Build succeeds',
                        'status': 'FAIL',
                        'reasoning': f'Build error: {str(e)}',
                    }
                ],
                'build_result': {
                    'exit_code': -1,
                    'stdout': '',
                    'stderr': str(e),
                    'success': False,
                },
            }
