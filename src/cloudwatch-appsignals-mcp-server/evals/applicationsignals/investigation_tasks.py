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

"""Service investigation tasks for Application Signals MCP evaluation."""

from evals.core import (
    FinalResponseCaptor,
    LLMJudgeValidator,
    Task,
    ToolCallsCaptor,
    ValidationPromptType,
)
from pathlib import Path


# MCP server file path
SERVER_PATH = (
    Path(__file__).parent.parent.parent
    / 'awslabs'
    / 'cloudwatch_appsignals_mcp_server'
    / 'server.py'
)
# MCP server working directory (cloudwatch-appsignals-mcp-server root)
SERVER_CWD = Path(__file__).parent.parent.parent

# Fixtures directory for investigation task mocks
FIXTURES_DIR = Path(__file__).parent / 'fixtures'


class ServiceInvestigationTask(Task):
    """Task for evaluating service health investigation and root cause analysis."""

    def __init__(
        self,
        id: str,
        prompt: str,
        expected_tools: list[str],
        validation_rubric: list[str],
        mock_config: dict = None,
        fixtures_dir: Path = None,
    ):
        """Initialize ServiceInvestigationTask.

        Args:
            id: Task identifier
            prompt: Investigation prompt
            expected_tools: Expected MCP tools to be called
            validation_rubric: Criteria for validating investigation quality
            mock_config: Mock configuration for AWS APIs
            fixtures_dir: Base directory for fixture files
        """
        super().__init__(
            id=id,
            expected_tools=expected_tools,
            mock_config=mock_config,
            fixtures_dir=fixtures_dir,
        )
        self.prompt_text = prompt
        self.validation_rubric = validation_rubric

    def get_prompt(self, working_directory: Path) -> str:
        """Return the investigation prompt."""
        return self.prompt_text

    @property
    def rubric(self) -> list[str]:
        """Return validation rubric."""
        return self.validation_rubric

    def get_captors(self, working_directory: Path):
        """Return captors for this task."""
        return [
            ToolCallsCaptor(),
            FinalResponseCaptor(),
        ]

    def get_validators(self, working_directory: Path):
        """Return validators for this task."""
        from evals.core.llm_provider import BedrockLLMProvider

        llm_provider = BedrockLLMProvider()

        return [
            LLMJudgeValidator(
                validation_prompt_type=ValidationPromptType.DATA_INTERPRETATION,
                llm_provider=llm_provider,
                rubric=self.rubric,
            )
        ]

    def get_server_file(self) -> Path:
        """Return MCP server file path."""
        return SERVER_PATH

    def get_server_root_directory(self) -> Path:
        """Return MCP server root directory."""
        return SERVER_CWD


# Task definitions
TASKS = [
    ServiceInvestigationTask(
        id='petclinic_scheduling_rca',
        prompt="""The PetClinic application is experiencing issues with the scheduling availability feature.
Users are reporting that they cannot book appointments. Can you investigate what's causing this problem?""",
        expected_tools=['audit_services'],
        validation_rubric=[
            'Agent called audit_services to investigate PetClinic',
            'Agent identified the POST /appointments operation with issues',
            'Agent recognized elevated error rates (12.5%) or availability problems',
            'Agent identified DynamoDB as the problematic dependency',
            'Root cause identified: DynamoDB ProvisionedThroughputExceededException',
            'Response explains the causal chain (PetClinic → SchedulingService → DynamoDB throttling)',
            'Recommendations provided (increase DynamoDB capacity, enable auto-scaling, implement retries, or add caching)',
        ],
        fixtures_dir=FIXTURES_DIR,
        mock_config={
            'boto3': {
                'application-signals': {
                    'list_services': [
                        {
                            'request': {},
                            'response': 'investigation/list_services/checkout_service.json',
                        }
                    ],
                    'list_audit_findings': [
                        {
                            'request': {},
                            'response': 'investigation/list_audit_findings/petclinic_scheduling.json',
                        }
                    ],
                }
            }
        },
    ),
    ServiceInvestigationTask(
        id='slo_breach_detailed_investigation',
        prompt="""I noticed some SLO alerts for CheckoutService. Can you investigate which SLOs are breached
and provide detailed information about their configuration and current status?""",
        expected_tools=['audit_services', 'get_slo'],
        validation_rubric=[
            'Agent called audit_services to discover breached SLOs',
            'Agent identified CheckoutService has 2 breached SLOs (Availability and Latency)',
            'Agent called get_slo to get detailed configuration for at least one breached SLO',
            'Response includes SLO configuration details (attainment goal, current attainment, interval)',
            'Response explains the breach severity (Availability: 94.2% vs 99.5% target)',
            'Response provides actionable insights based on both audit findings and SLO configuration',
        ],
        fixtures_dir=FIXTURES_DIR,
        mock_config={
            'boto3': {
                'application-signals': {
                    'list_services': [
                        {
                            'request': {},
                            'response': 'investigation/list_services/checkout_service.json',
                        }
                    ],
                    'list_audit_findings': [
                        {
                            'request': {},
                            'response': 'investigation/list_audit_findings/slo_breach_investigation.json',
                        }
                    ],
                    'list_service_level_objectives': [
                        {
                            'request': {},
                            'response': 'investigation/list_service_level_objectives/checkout_service_slos.json',
                        }
                    ],
                    'get_service_level_objective': [
                        {
                            'request': {'Id': 'CheckoutService-Availability'},
                            'response': 'investigation/get_service_level_objective/checkout_availability_slo.json',
                        },
                        {
                            'request': {'Id': 'CheckoutService-Latency'},
                            'response': 'investigation/get_service_level_objective/checkout_latency_slo.json',
                        },
                    ],
                    'get_service': [
                        {
                            'request': {
                                'KeyAttributes': {
                                    'Name': 'CheckoutService',
                                    'Type': 'Service',
                                    'Environment': 'prod',
                                }
                            },
                            'response': 'investigation/get_service/checkout_service_detail.json',
                        }
                    ],
                },
                'cloudwatch': {
                    'get_metric_data': [
                        {
                            'request': {},
                            'response': 'investigation/get_metric_data/checkout_service_metrics.json',
                        }
                    ],
                },
                'xray': {
                    'get_trace_segment_destination': [
                        {
                            'request': {},
                            'response': 'investigation/get_trace_segment_destination/cloudwatch_logs.json',
                        }
                    ],
                },
            }
        },
    ),
]
