"""
LLM Client Module

Wraps litellm.completion with retry logic, rate limiting, and observability.
"""

import json
import time
import threading
import tenacity
import sentry_sdk
import structlog

import litellm


logger = structlog.get_logger()


class RateLimiter:
    """Simple token bucket rate limiter for LLM API calls."""
    
    def __init__(self, max_requests_per_minute: int = 60):
        self.max_requests_per_minute = max_requests_per_minute
        self.requests_this_minute = 0
        self.minute_start = time.time()
        self._lock = threading.Lock()
    
    def acquire(self):
        """Block until a request slot is available."""
        with self._lock:
            now = time.time()
            # Reset counter if minute has passed
            if now - self.minute_start >= 60:
                self.requests_this_minute = 0
                self.minute_start = now
            
            # If at limit, wait until next minute
            if self.requests_this_minute >= self.max_requests_per_minute:
                wait_time = 60 - (now - self.minute_start)
                if wait_time > 0:
                    logger.warning("llm.rate_limited", wait_time=wait_time)
                    time.sleep(wait_time)
                self.requests_this_minute = 0
                self.minute_start = time.time()
            
            self.requests_this_minute += 1


class LLMClient:
    """
    LLM API client with retry logic and observability.
    
    Encapsulates:
    - API calls to LiteLLM
    - Retry logic via tenacity
    - Rate limiting via token bucket
    - Sentry spans for tracing
    - Token usage tracking
    """
    
    def __init__(self, model: str, api_key: str, rate_limiter: RateLimiter = None):
        """
        Initialize the LLM client.
        
        Args:
            model: Model name (e.g., "deepseek/deepseek-v4-flash")
            api_key: API key for the model
            rate_limiter: Optional RateLimiter for throttling calls
        """
        self.model = model
        self.api_key = api_key
        self.rate_limiter = rate_limiter or RateLimiter()
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
        # Apply rate limiting before making the call
        self.rate_limiter.acquire()
        
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
