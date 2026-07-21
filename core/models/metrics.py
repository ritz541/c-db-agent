from pydantic import BaseModel, Field


class StepMetrics(BaseModel):
    step_id: int
    scheduled_at: float
    started_at: float
    finished_at: float
    wait_time: float = 0.0  # started_at - scheduled_at
    execution_time: float = 0.0  # finished_at - started_at


class SchedulerMetrics(BaseModel):
    run_id: str = ""
    total_wall_time: float = 0.0
    average_wait_time: float = 0.0
    average_execution_time: float = 0.0
    critical_path_duration: float = 0.0
    parallel_efficiency: float = 0.0
    peak_concurrency: int = 0
    queue_depth_peak: int = 0
    retry_count: int = 0
    step_metrics: dict[int, StepMetrics] = Field(default_factory=dict)
