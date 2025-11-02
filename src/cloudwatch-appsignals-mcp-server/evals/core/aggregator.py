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

"""Result aggregation logic extracted from EvalRunner.

This module implements the Single Responsibility Principle (SRP) by extracting
result aggregation into a focused class.

Before: Result aggregation was mixed with execution logic in EvalRunner.run_task()
After: ResultAggregator handles just result aggregation (single responsibility)

Benefits:
- Easier to test (just pass in mock prompt results)
- Easier to modify (change aggregation logic without touching execution)
- Clearer separation between "doing work" and "summarizing results"
"""

from typing import Any, Dict, List


class ResultAggregator:
    """Aggregates results from multiple prompt executions.

    Responsibilities:
    1. Determine overall task success from multiple prompt results
    2. Format final result dictionary structure

    This class follows SRP: it has ONE reason to change - if the way we
    aggregate and format results changes.

    Example:
        aggregator = ResultAggregator()

        # Assume we executed 3 prompts
        prompt_results = [
            {'success': True, 'metrics': {...}, ...},
            {'success': True, 'metrics': {...}, ...},
            {'success': False, 'metrics': {...}, ...},
        ]

        # Aggregate into final task result
        task_result = aggregator.aggregate_task_results(
            task_id='my_task',
            prompt_results=prompt_results
        )

        # Returns:
        # {
        #     'task_id': 'my_task',
        #     'success': False,  # Because one prompt failed
        #     'num_prompts': 3,
        #     'prompt_results': [...]
        # }
    """

    def aggregate_task_results(
        self, task_id: str, prompt_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Aggregate results from multiple prompts into final task result.

        Args:
            task_id: ID of the task
            prompt_results: List of result dictionaries from PromptExecutor

        Returns:
            Final task result dictionary with overall success status
            {
                'task_id': str,
                'success': bool,
                'num_prompts': int,
                'prompt_results': List[Dict]
            }
        """
        # Task passes only if ALL prompts pass
        overall_task_pass = all(r['success'] for r in prompt_results)

        return {
            'task_id': task_id,
            'success': overall_task_pass,
            'num_prompts': len(prompt_results),
            'prompt_results': prompt_results,
        }
