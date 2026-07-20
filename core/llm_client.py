"""
LLM Client Module

Wraps litellm.completion with retry logic and observability.
"""

import json
import tenacity
import sentry_sdk
import structlog

import litellm


logger = structlog.get_logger()


class LLMClient:
    """
    LLM API client with retry logic and observability.
    
    Encapsulates:
    - API calls to LiteLLM
    - Retry logic via tenacity
    - Sentry spans for tracing
    - Token usage tracking
    """
    
    def __init__(self, model: str, api_key: str):
        """
        Initialize the LLM client.
        
        Args:
            model: Model name (e.g., "deepseek/deepseek-v4-flash")
            api_key: API key for the model
        """
        self.model = model
        self.api_key = api_key
        logger.info("llm_client.initialized", model=model)
    
    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
        stop=tenacity.stop_after_attempt(3),
        reraise=True,
        before_sleep=lambda retry_state: logger.warning(
            "llm.retry",
            attempt=retry_state.attempt_number,
            wait=retry_state.next_action.sleep,
        ),
    )
    def complete(self, messages: list, tools: list = None) -> dict:
        """
        Call LLM API with retry logic.
        
        Args:
            messages: Conversation history
            tools: Tool definitions (OpenAI format)
        
        Returns:
            dict: LLM response
        """
        # Debug: log the last 3 messages to see what we're sending
        for i, msg in enumerate(messages[-3:]):
            role = msg.get("role", "unknown")
            has_tool_calls = bool(msg.get("tool_calls"))
            content_preview = str(msg.get("content", ""))[:50]
            logger.debug(
                "llm.messages_preview",
                index=len(messages) - 3 + i,
                role=role,
                has_tool_calls=has_tool_calls,
                content=content_preview
            )
        
        logger.info("llm.calling", message_count=len(messages))
        
        with sentry_sdk.start_span(op="llm", description=self.model) as span:
            span.set_tag("llm.model", self.model)
            
            # Build kwargs
            kwargs = {
                "model": self.model,
                "messages": messages,
                "api_key": self.api_key,
            }
            
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            
            # Call API
            response = litellm.completion(**kwargs)
            
            # Extract token usage if available
            if hasattr(response, "usage") and response.usage:
                usage = response.usage
                if hasattr(usage, "prompt_tokens"):
                    span.set_data("llm.tokens.input", usage.prompt_tokens)
                    span.set_data("llm.tokens.output", usage.completion_tokens)
                    span.set_data("llm.tokens.total", usage.total_tokens)
            
            logger.info(
                "llm.responded",
                has_tool_calls=bool(response.choices[0].message.tool_calls)
            )
            
            return response
    
    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
        stop=tenacity.stop_after_attempt(3),
        reraise=True,
        before_sleep=lambda retry_state: logger.warning(
            "llm.stream_retry",
            attempt=retry_state.attempt_number,
            wait=retry_state.next_action.sleep,
        ),
    )
    def complete_stream(self, messages: list, tools: list = None):
        """
        Call LLM API with streaming. Yields tokens as they arrive.
        
        Args:
            messages: Conversation history
            tools: Tool definitions (OpenAI format)
        
        Yields:
            str: Text tokens as they arrive from the LLM
        """
        logger.info("llm.stream_start", message_count=len(messages))
        
        # Build kwargs
        kwargs = {
            "model": self.model,
            "messages": messages,
            "api_key": self.api_key,
            "stream": True,
        }
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        # Call API with streaming
        response = litellm.completion(**kwargs)
        
        full_content = ""
        tool_calls_detected = False
        
        for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue
            
            # Check for content tokens
            if delta.content:
                full_content += delta.content
                yield delta.content
            
            # Check for tool calls (we can't stream tool calls)
            if delta.tool_calls:
                tool_calls_detected = True
        
        logger.info(
            "llm.stream_end",
            char_count=len(full_content),
            has_tool_calls=tool_calls_detected,
        )
