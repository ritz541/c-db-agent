from abc import ABC, abstractmethod
from core.models.context import ExecutionContext
from core.models.llm import LLMResponse
from core.models.message import AgentMessage
from core.models.tool import ToolMetadata


class LLMProviderInterface(ABC):
    @abstractmethod
    async def generate_response(
        self,
        messages: list[AgentMessage],
        tools: list[ToolMetadata] | None = None,
        context: ExecutionContext | None = None,
    ) -> LLMResponse:
        """Generate response from LLM."""
        pass
