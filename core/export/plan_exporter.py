from typing import Any
from core.models.planning import Plan


STATUS_STYLES = {
    "completed": "fill:#d4edda,stroke:#28a745",
    "failed": "fill:#f8d7da,stroke:#dc3545",
    "cancelled": "fill:#e2e3e5,stroke:#6c757d",
    "running": "fill:#fff3cd,stroke:#ffc107",
    "pending": "fill:#ffffff,stroke:#6c757d",
}


class MermaidExporter:
    """Exporter that renders a Plan DAG as a Mermaid graph string."""

    @classmethod
    def export(cls, plan: Plan) -> str:
        lines: list[str] = ["graph TD"]

        # Declare step nodes
        for step in plan.steps:
            node_id = f"step_{step.step_id}"
            safe_desc = step.description.replace('"', '\\"')
            label = f"Step {step.step_id}: {safe_desc}"
            lines.append(f'    {node_id}["{label}"]')

        # Declare dependency edges
        for step in plan.steps:
            node_id = f"step_{step.step_id}"
            for dep_id in step.depends_on:
                dep_node_id = f"step_{dep_id}"
                lines.append(f"    {dep_node_id} --> {node_id}")

        # Declare status styling
        for step in plan.steps:
            node_id = f"step_{step.step_id}"
            style_str = STATUS_STYLES.get(step.status, STATUS_STYLES["pending"])
            lines.append(f"    style {node_id} {style_str}")

        return "\n".join(lines)


class PlanExporter:
    """Presentation facade for exporting Plan domain models to formatted presentation strings."""

    def __init__(self, plan: Plan) -> None:
        self.plan = plan

    def to_mermaid(self) -> str:
        return MermaidExporter.export(self.plan)

    def export_to(self, format: str = "mermaid") -> str:
        if format.lower() == "mermaid":
            return MermaidExporter.export(self.plan)
        raise ValueError(f"Unsupported export format: '{format}'")

    @classmethod
    def export(cls, plan: Plan, format: str = "mermaid") -> str:
        if format.lower() == "mermaid":
            return MermaidExporter.export(plan)
        raise ValueError(f"Unsupported export format: '{format}'")
