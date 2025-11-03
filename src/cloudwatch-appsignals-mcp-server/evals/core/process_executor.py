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

"""Process execution abstraction for evaluation framework.

Provides a pluggable interface for executing shell commands and subprocesses,
enabling better testability and mocking.
"""

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ProcessResult:
    """Result of a subprocess execution.

    Attributes:
        returncode: Process exit code
        stdout: Standard output as string
        stderr: Standard error as string
    """

    returncode: int
    stdout: str
    stderr: str


class ProcessExecutor(ABC):
    """Abstract base class for process execution.

    Implementations provide different ways to execute shell commands
    (real subprocess, mocked, sandboxed, etc.).
    """

    @abstractmethod
    def run(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> ProcessResult:
        """Execute a command and return result.

        Args:
            cmd: Command and arguments as list (e.g., ['git', 'diff'])
            cwd: Working directory for command execution
            timeout: Timeout in seconds (None for no timeout)

        Returns:
            ProcessResult with returncode, stdout, stderr

        Raises:
            subprocess.TimeoutExpired: If command times out
            Exception: If command execution fails
        """
        pass


class SubprocessExecutor(ProcessExecutor):
    """Real subprocess executor using Python's subprocess module.

    This is the default implementation that actually executes commands.
    """

    def run(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> ProcessResult:
        """Execute a command using subprocess.run().

        Args:
            cmd: Command and arguments as list
            cwd: Working directory for command execution
            timeout: Timeout in seconds

        Returns:
            ProcessResult with returncode, stdout, stderr

        Raises:
            subprocess.TimeoutExpired: If command times out
            Exception: If command execution fails
        """
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return ProcessResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
