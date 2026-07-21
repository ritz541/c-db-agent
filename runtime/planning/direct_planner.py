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

        STOP_WORDS = {
            "a", "an", "the", "in", "on", "at", "to", "of", "for", "is", "are", "be",
            "by", "with", "or", "and", "so", "my", "me", "you", "your", "what", "how",
            "can", "do", "does", "did", "it", "this", "that", "i", "we", "he", "she",
        }

        matching_tool = None
        goal_words = set(goal.lower().split())
        for tool in tools:
            if tool.name in goal.lower():
                matching_tool = tool.name
                break
            desc_keywords = [
                w.strip(".,!?()[]{}").lower()
                for w in tool.description.split()[:5]
            ]
            meaningful_keywords = [w for w in desc_keywords if w and w not in STOP_WORDS and len(w) > 2]
            if any(kw in goal_words for kw in meaningful_keywords):
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
