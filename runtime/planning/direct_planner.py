from uuid import uuid4
import structlog

from core.interfaces.llm import LLMProviderInterface
from core.interfaces.planner import PlannerInterface
from core.models.context import ExecutionContext
from core.models.message import AgentMessage
from core.models.planning import Plan, PlanCategory, PlanStep
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

        matching_tool = None
        goal_lower = goal.lower()
        for tool in tools:
            if tool.name.lower() in goal_lower:
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

        is_simple_retrieval = matching_tool is not None and len(steps) == 1
        category = PlanCategory.SIMPLE_RETRIEVAL if is_simple_retrieval else PlanCategory.GENERAL
        metadata = {"single_pass": True} if is_simple_retrieval else {}

        plan = Plan(
            plan_id=plan_id,
            goal=goal,
            category=category,
            steps=steps,
            completed=False,
            metadata=metadata,
        )
        logger.info("planner.plan_created", plan_id=plan_id, goal=goal)
        return plan
