from typing import Any
import litellm
import structlog

from core.errors.exceptions import LLMProviderError
from core.interfaces.llm import LLMProviderInterface
from core.models.context import ExecutionContext
from core.models.llm import LLMResponse
from core.models.message import AgentMessage
from core.models.tool import ToolCall, ToolMetadata

logger = structlog.get_logger(__name__)


class LiteLLMProvider(LLMProviderInterface):
    """LiteLLM Provider implementation of LLMProviderInterface."""

    def __init__(
        self,
        model: str = "deepseek/deepseek-chat",
        api_key: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        **extra_kwargs: Any,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.extra_kwargs = extra_kwargs

    async def generate_response(
        self,
        messages: list[AgentMessage],
        tools: list[ToolMetadata] | None = None,
        context: ExecutionContext | None = None,
    ) -> LLMResponse:
        # Convert AgentMessage objects to LiteLLM message dicts
        formatted_messages = []
        for msg in messages:
            msg_dict: dict[str, Any] = {"role": msg.role, "content": msg.content or ""}
            if msg.name:
                msg_dict["name"] = msg.name
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": (
                                tc.arguments
                                if isinstance(tc.arguments, str)
                                else litellm.json.dumps(tc.arguments)
                                if hasattr(litellm, "json")
                                else str(tc.arguments)
                            ),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            formatted_messages.append(msg_dict)

        # Convert ToolMetadata to OpenAI tool format
        formatted_tools = None
        if tools:
            formatted_tools = []
            for tool in tools:
                formatted_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters
                            or {"type": "object", "properties": {}},
                        },
                    }
                )

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": self.temperature,
            **self.extra_kwargs,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens
        if formatted_tools:
            kwargs["tools"] = formatted_tools

        try:
            # Use litellm.acompletion or sync completion fallback
            response = await litellm.acompletion(**kwargs)
            choice = response.choices[0].message
            content = choice.content

            parsed_tool_calls: list[ToolCall] = []
            if getattr(choice, "tool_calls", None):
                for tc in choice.tool_calls:
                    func = tc.function
                    args = func.arguments
                    if isinstance(args, str):
                        try:
                            import json

                            args = json.loads(args)
                        except Exception:
                            args = {"raw": args}
                    parsed_tool_calls.append(
                        ToolCall(id=tc.id, name=func.name, arguments=args)
                    )

            metadata = {
                "model": response.model if hasattr(response, "model") else self.model,
                "usage": (
                    response.usage.model_dump()
                    if hasattr(response.usage, "model_dump")
                    else dict(response.usage)
                    if hasattr(response, "usage") and response.usage
                    else {}
                ),
            }

            return LLMResponse(
                content=content,
                tool_calls=parsed_tool_calls,
                metadata=metadata,
            )
        except Exception as e:
            logger.error("litellm_provider.error", error=str(e), model=self.model)
            raise LLMProviderError(f"LiteLLM Provider error: {e}") from e
