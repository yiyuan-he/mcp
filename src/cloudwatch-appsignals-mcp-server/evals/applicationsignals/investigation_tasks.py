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

"""Service investigation tasks for Application Signals MCP evaluation.

Demonstrates how to evaluate complex investigative workflows where the agent must:
1. Call audit tools to gather comprehensive evidence
2. Interpret findings from multiple auditors (slo, operation_metric, trace, dependency_metric)
3. Perform root cause analysis from audit results
4. Provide actionable insights based on findings

These tasks range from simple health checks to complex multi-auditor investigations,
showcasing the eval framework's ability to handle read-only investigative workflows.
"""

from evals.core import FinalResponseCaptor, LLMJudgeValidator, Task, ToolCallsCaptor
from evals.core.constants import DATA_INTERPRETATION_VALIDATION_PROMPT
from pathlib import Path


# Server path for this tool
SERVER_PATH = (
    Path(__file__).parent.parent.parent
    / 'awslabs'
    / 'cloudwatch_appsignals_mcp_server'
    / 'server.py'
)

# Fixtures directory for investigation task mocks
FIXTURES_DIR = Path(__file__).parent / 'fixtures'


class ServiceInvestigationTask(Task):
    """Task for evaluating service health investigation and root cause analysis.

    This task type evaluates the agent's ability to:
    - Use audit_services() tool effectively with appropriate auditor selection
    - Navigate complex observability scenarios
    - Interpret findings from multiple auditors (slo, operation_metric, trace, dependency_metric)
    - Correlate data across metrics, traces, logs, and dependencies
    - Identify root causes from audit findings
    - Provide actionable recommendations

    Unlike code modification tasks, these are read-only investigations that test
    the agent's analytical and interpretive capabilities.
    """

    def __init__(
        self,
        id: str,
        prompt: str,
        expected_tools: list[str],
        validation_rubric: list[str],
        mocks: dict = None,
        fixtures_dir: Path = None,
        max_turns: int = 15,
    ):
        """Initialize ServiceInvestigationTask.

        Args:
            id: Task identifier
            prompt: Investigation prompt (e.g., "Why is pet clinic having issues?")
            expected_tools: Expected MCP tools to be called (typically ['audit_services'])
            validation_rubric: Criteria for validating investigation quality
            mocks: Mock configuration for AWS APIs (optional)
            fixtures_dir: Base directory for fixture files (required if using fixture references)
            max_turns: Maximum conversation turns (default: 15 for complex investigations)
        """
        super().__init__(
            id=id,
            max_turns=max_turns,
            expected_tools=expected_tools,
            mocks=mocks,
            fixtures_dir=fixtures_dir,
        )
        self.prompt_text = prompt
        self.validation_rubric = validation_rubric

    def get_prompts(self, context: dict) -> list[str]:
        """Return the investigation prompt.

        Args:
            context: Runtime context (unused)

        Returns:
            List with single investigation prompt
        """
        return [self.prompt_text]

    @property
    def rubric(self) -> list[str]:
        """Return validation rubric."""
        return self.validation_rubric

    def get_captors(self, context: dict):
        """Return captors for this task.

        For investigation tasks, we capture:
        - Tool calls: To verify investigative workflow
        - Final response: To validate conclusions and recommendations

        Args:
            context: Runtime context (unused)

        Returns:
            List of captors
        """
        return [
            ToolCallsCaptor(),  # Capture investigation workflow
            FinalResponseCaptor(),  # Capture findings and recommendations
        ]

    def get_validators(self, context: dict):
        """Return validators for this task.

        Uses LLM judge to evaluate investigation quality.

        Args:
            context: Runtime context (unused)

        Returns:
            List with single LLMJudgeValidator
        """
        return [
            LLMJudgeValidator(validation_prompt_template=DATA_INTERPRETATION_VALIDATION_PROMPT)
        ]


# Task definitions demonstrating range of complexity

TASKS = [
    # Complex: Multi-auditor root cause analysis - DynamoDB throttling
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
        mocks={
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
        max_turns=20,  # Complex investigation may need more turns
    ),
    # Multi-tool: SLO breach investigation with detailed SLO inspection
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
        mocks={
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
                }
            }
        },
        max_turns=20,
    ),
]
