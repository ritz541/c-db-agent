from uuid import uuid4
import structlog

from core.interfaces.llm import LLMProviderInterface
from core.interfaces.planner import PlannerInterface
from core.models.context import ExecutionContext
from core.models.message import AgentMessage
from core.models.planning import Plan, PlanStep
from core.models.tool import ToolMetadata

logger = structlog.get_logger(__name__)


class DirectPlanner(PlannerInterface):
    """Direct Planner implementation of PlannerInterface."""

    def __init__(self, llm_provider: LLMProviderInterface | None = None) -> None:
        self.llm_provider = llm_provider

    async def create_plan(
        self,
        goal: str,
        history: list[AgentMessage],
        tools: list[ToolMetadata],
        context: ExecutionContext | None = None,
    ) -> Plan:
        plan_id = str(uuid4())
        steps: list[PlanStep] = []

        # If goal mentions math/calculation and calculator tool exists
        matching_tool = None
        for tool in tools:
            if tool.name in goal.lower() or any(
                kw in goal.lower() for kw in tool.description.lower().split()[:3]
            ):
                matching_tool = tool.name
                break

        steps.append(
            PlanStep(
                step_id=1,
                description=f"Process goal: {goal}",
                tool_name=matching_tool,
                node_type="tool" if matching_tool else "custom",
                completed=False,
            )
        )

        plan = Plan(
            plan_id=plan_id,
            goal=goal,
            steps=steps,
            completed=False,
        )
        logger.info("planner.plan_created", plan_id=plan_id, goal=goal)
        return plan
