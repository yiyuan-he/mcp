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

"""LLM provider abstraction for evaluation framework.

Provides a pluggable interface for different LLM providers (Bedrock, OpenAI, Anthropic, etc.)
to decouple validators from specific LLM implementations.
"""

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Implementations provide text generation capabilities from different
    LLM services (AWS Bedrock, OpenAI, Anthropic API, local models, etc.).
    """

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate text from the LLM.

        Args:
            prompt: The prompt text to send to the LLM

        Returns:
            Generated text response from the LLM

        Raises:
            Exception: If LLM call fails
        """
        pass


class BedrockLLMProvider(LLMProvider):
    """AWS Bedrock LLM provider implementation.

    Uses boto3 Bedrock Runtime client to generate responses.
    """

    def __init__(self, bedrock_client: Any, model_id: str = None, temperature: float = None):
        """Initialize Bedrock LLM provider.

        Args:
            bedrock_client: Boto3 Bedrock Runtime client
            model_id: Optional model ID (defaults to framework default)
            temperature: Optional temperature (defaults to framework default)
        """
        self.bedrock_client = bedrock_client
        self.model_id = model_id
        self.temperature = temperature

    async def generate(self, prompt: str) -> str:
        """Generate text using AWS Bedrock.

        Args:
            prompt: The prompt text to send to Bedrock

        Returns:
            Generated text response

        Raises:
            Exception: If Bedrock API call fails
        """
        from .constants import DEFAULT_MODEL_ID, DEFAULT_TEMPERATURE

        model_id = self.model_id or DEFAULT_MODEL_ID
        temperature = self.temperature if self.temperature is not None else DEFAULT_TEMPERATURE

        response = self.bedrock_client.converse(
            modelId=model_id,
            messages=[{'role': 'user', 'content': [{'text': prompt}]}],
            inferenceConfig={'temperature': temperature},
        )

        return response['output']['message']['content'][0]['text']
