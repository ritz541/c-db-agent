import json

import inspect
from typing import Any
import structlog

from core.errors.exceptions import ToolExecutionError
from core.interfaces.executor import ExecutorInterface
from core.interfaces.tool import ToolInterface
from core.models.context import ExecutionContext
from core.models.tool import ToolCall, ToolResult

logger = structlog.get_logger(__name__)


class ToolExecutor(ExecutorInterface):
    """Tool Executor implementation of ExecutorInterface."""

    def __init__(self, tools: list[ToolInterface] | None = None) -> None:
        self._tools: dict[str, ToolInterface] = {}
        if tools:
            for tool in tools:
                self.register_tool(tool)

    def register_tool(self, tool: ToolInterface) -> None:
        name = tool.metadata.name
        self._tools[name] = tool
        logger.info("tool_executor.registered", tool_name=name)

    def get_tool(self, name: str) -> ToolInterface | None:
        return self._tools.get(name)

    def list_tool_metadata(self) -> list[Any]:
        return [tool.metadata for tool in self._tools.values()]

    async def execute_tool(
        self,
        tool_call: ToolCall,
        context: ExecutionContext | None = None,
    ) -> ToolResult:
        tool = self._tools.get(tool_call.name)
        if not tool:
            err_msg = f"Tool '{tool_call.name}' is not registered."
            logger.error("tool_executor.not_found", tool_name=tool_call.name)
            return ToolResult(
                tool_call_id=tool_call.id,
                success=False,
                output="",
                error=err_msg,
            )

        db_conn = None
        should_return_conn = False
        try:
            from infrastructure.db_pool import get_connection
            db_conn = get_connection()
            should_return_conn = True
        except Exception:
            pass

        try:
            logger.info("tool_executor.executing", tool_name=tool_call.name)
            args = tool_call.arguments or {}

            sig = inspect.signature(tool.execute)
            has_var_kw = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )

            exec_kwargs: dict[str, Any] = {}
            if "db_conn" in sig.parameters or has_var_kw:
                exec_kwargs["db_conn"] = db_conn
            if "context" in sig.parameters or has_var_kw:
                exec_kwargs["context"] = context

            for k, v in args.items():
                if k in sig.parameters or has_var_kw:
                    exec_kwargs[k] = v

            res = tool.execute(**exec_kwargs)
            if inspect.isawaitable(res):
                res = await res

            if isinstance(res, ToolResult):
                return res
            elif isinstance(res, dict):
                if "output" in res and isinstance(res["output"], str):
                    output_str = res["output"]
                else:
                    try:
                        output_str = json.dumps(res, default=str)
                    except Exception:
                        output_str = str(res)
                return ToolResult(
                    tool_call_id=tool_call.id,
                    success=res.get("success", True),
                    output=output_str,
                    error=res.get("error"),
                    metadata=res.get("metadata", {}),
                )
            else:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    success=True,
                    output=str(res),
                )
        except Exception as e:
            err_str = f"Error executing tool '{tool_call.name}': {e}"
            logger.error("tool_executor.failed", tool_name=tool_call.name, error=str(e))
            return ToolResult(
                tool_call_id=tool_call.id,
                success=False,
                output="",
                error=err_str,
            )
        finally:
            if db_conn and should_return_conn:
                try:
                    from infrastructure.db_pool import return_connection
                    return_connection(db_conn)
                except Exception:
                    pass
