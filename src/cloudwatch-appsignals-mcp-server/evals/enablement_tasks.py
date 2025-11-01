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

"""Enablement task for Application Signals MCP evaluation.

Evaluates whether the AI agent can use the get_enablement_guide tool
to enable Application Signals monitoring on various platforms.
"""

import subprocess
from loguru import logger
from pathlib import Path
from typing import Optional

from framework import (
    Task,
    GitDiffCaptor,
    LLMJudgeValidator,
    BuildValidator,
)


# Server path for this tool
SERVER_PATH = Path(__file__).parent.parent / 'awslabs' / 'cloudwatch_appsignals_mcp_server' / 'server.py'


class EnablementTask(Task):
    """Task for evaluating Application Signals enablement.

    Tests whether the agent can:
    1. Call get_enablement_guide MCP tool correctly
    2. Understand the returned enablement instructions
    3. Modify IaC and application files appropriately
    4. Pass build validation and rubric criteria
    """

    def __init__(
        self,
        id: str,
        git_paths: list[str],
        iac_dir: str,
        app_dir: str,
        language: str,
        framework: str,
        platform: str,
        validation_rubric: list[str],
        expected_tools: list[str] = None,
        build_command: Optional[str] = None,
        build_working_dir: Optional[str] = None,
        modifies_code: bool = True,
        max_turns: int = 20,
    ):
        """Initialize EnablementTask.

        Args:
            id: Task identifier
            git_paths: List of paths (relative to mcp_repo_root) for git diff/cleanup
            iac_dir: IaC directory path (relative to mcp_repo_root)
            app_dir: Application directory path (relative to mcp_repo_root)
            language: Programming language (e.g., 'python', 'java')
            framework: Framework (e.g., 'flask', 'spring-boot')
            platform: Platform (e.g., 'ec2', 'ecs', 'eks')
            validation_rubric: List of validation criteria
            expected_tools: Expected MCP tools to be called
            build_command: Optional build command (e.g., 'npm install && npm run build')
            build_working_dir: Optional build working directory (relative to mcp_repo_root)
            modifies_code: Whether task modifies files (for cleanup)
            max_turns: Maximum conversation turns
        """
        super().__init__(id=id, max_turns=max_turns)
        self.git_paths = git_paths
        self.iac_dir = iac_dir
        self.app_dir = app_dir
        self.language = language
        self.framework = framework
        self.platform = platform
        self.validation_rubric = validation_rubric
        self.expected_tools = expected_tools or ['get_enablement_guide']
        self.build_command = build_command
        self.build_working_dir = build_working_dir
        self.modifies_code = modifies_code

    def get_prompt_for_project(self, mcp_repo_root: Path) -> list[str]:
        """Return enablement prompt with absolute paths.

        Args:
            mcp_repo_root: Absolute path to MCP repository root

        Returns:
            List with single prompt
        """
        iac_abs_path = mcp_repo_root / self.iac_dir
        app_abs_path = mcp_repo_root / self.app_dir

        prompt = f"""Enable Application Signals for my {self.language} {self.framework} on {self.platform}.

My infrastructure as code directory is: {iac_abs_path}
My application directory is: {app_abs_path}"""

        return [prompt]

    def get_prompt(self) -> list[str]:
        """This should not be called directly. Use get_prompt_for_project() instead."""
        raise NotImplementedError(
            "Use get_prompt_for_project(mcp_repo_root) instead to provide absolute paths"
        )

    @property
    def rubric(self) -> list[str]:
        """Return validation rubric."""
        return self.validation_rubric

    def get_captors(self):
        """Return captors for this task.

        Captures git diff to evaluate code modifications.
        """
        from framework import GitDiffCaptor

        return [GitDiffCaptor(git_paths=self.git_paths)]

    def get_validators_for_project(self, mcp_repo_root: Path):
        """Return validators for this task.

        Args:
            mcp_repo_root: Absolute path to MCP repository root

        Returns:
            List of validators (BuildValidator and LLMJudgeValidator)
        """
        from framework import BuildValidator, LLMJudgeValidator
        from framework.constants import CODE_MODIFICATION_VALIDATION_PROMPT

        validators = []

        # Add build validator if build config provided
        if self.build_command and self.build_working_dir:
            build_working_dir = mcp_repo_root / self.build_working_dir

            validators.append(
                BuildValidator(
                    command=self.build_command,
                    working_dir=build_working_dir,
                )
            )

        # Add LLM judge validator
        validators.append(
            LLMJudgeValidator(
                validation_prompt_template=CODE_MODIFICATION_VALIDATION_PROMPT
            )
        )

        return validators

    def get_validators(self):
        """This should not be called directly. Use get_validators_for_project() instead."""
        raise NotImplementedError(
            "Use get_validators_for_project(mcp_repo_root) instead to provide absolute paths"
        )

    def cleanup(self, mcp_repo_root: Path):
        """Clean up git changes made by enablement agent.

        Resets git state for paths specified in git_paths.

        Args:
            mcp_repo_root: Absolute path to MCP repository root
        """
        if not self.git_paths:
            logger.warning('No git_paths specified to clean')
            return

        try:
            for rel_path in self.git_paths:
                full_path = str(mcp_repo_root / rel_path)
                logger.debug(f'Cleaning path: {full_path}')
                subprocess.run(
                    ['git', 'checkout', 'HEAD', '--', full_path],
                    capture_output=True,
                    timeout=10,
                )
                subprocess.run(
                    ['git', 'clean', '-fd', full_path],
                    capture_output=True,
                    timeout=10,
                )
            logger.debug(f'Reset git state for: {", ".join(self.git_paths)}')
        except Exception as e:
            logger.warning(f'Failed to reset git state: {e}')


# Task definitions
TASKS = [
    EnablementTask(
        id="ec2_python_flask",
        git_paths=[
            "samples/cloudwatch-appsignals-mcp-server/get-enablement-guide-samples/infrastructure/ec2/cdk",
            "samples/cloudwatch-appsignals-mcp-server/get-enablement-guide-samples/sample-apps/python/flask",
        ],
        iac_dir="samples/cloudwatch-appsignals-mcp-server/get-enablement-guide-samples/infrastructure/ec2/cdk",
        app_dir="samples/cloudwatch-appsignals-mcp-server/get-enablement-guide-samples/sample-apps/python/flask",
        language="python",
        framework="flask",
        platform="ec2",
        build_command="npm install && npm run build",
        build_working_dir="samples/cloudwatch-appsignals-mcp-server/get-enablement-guide-samples/infrastructure/ec2/cdk",
        expected_tools=["get_enablement_guide"],
        modifies_code=True,
        validation_rubric=[
            "IAM: CloudWatchAgentServerPolicy is attached to EC2 instance role",
            "Prerequisites: System dependencies installed (wget, docker, python3-pip)",
            "CloudWatch Agent: Downloaded, installed, and configured with application_signals",
            "CloudWatch Agent: Started successfully using amazon-cloudwatch-agent-ctl",
            "ADOT: aws-opentelemetry-distro installed via pip3 in UserData",
            "Dockerfile (if Docker): Installs aws-opentelemetry-distro AND uses opentelemetry-instrument wrapper in CMD",
            "OTel Config: Basic exporters set (OTEL_METRICS_EXPORTER=none, OTEL_LOGS_EXPORTER=none, OTEL_AWS_APPLICATION_SIGNALS_ENABLED=true)",
            "OTel Config: Python-specific settings (OTEL_PYTHON_DISTRO=aws_distro, OTEL_PYTHON_CONFIGURATOR=aws_configurator)",
            "OTel Config: Protocol and sampling (OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf, OTEL_TRACES_SAMPLER=xray)",
            "OTel Config: Endpoints (OTEL_TRACES_SAMPLER_ARG with localhost:2000, OTEL_AWS_APPLICATION_SIGNALS_EXPORTER_ENDPOINT with localhost:4316/v1/metrics, OTEL_EXPORTER_OTLP_TRACES_ENDPOINT with localhost:4316/v1/traces)",
            "OTel Config: Service name resource attribute set",
            "Application Startup: If Docker, uses docker run with -e flags and --network host. If non-Docker, uses opentelemetry-instrument wrapper with export env vars.",
            "Code Integrity: Only IaC/Dockerfile modified, application code unchanged",
        ],
    ),
]
