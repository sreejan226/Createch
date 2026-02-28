from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from domain.models import OptimizationInput


@dataclass
class DemandForecast:
    demand_by_item_site_bucket: Dict[Tuple[str, str, int], float]


@dataclass
class ProductivityForecast:
    duration_by_task_bucket: Dict[str, int]  # task_id -> duration in buckets


def forecast_demand(opt_input: OptimizationInput) -> DemandForecast:
    """
    Stub demand forecast.

    For the 1-day prototype, we use a simple rule-based proxy that is
    ML-ready: same interface you would use for a LightGBM/XGBoost model.
    """
    demand: Dict[Tuple[str, str, int], float] = {}
    for bucket in opt_input.time_buckets:
        for task in opt_input.tasks:
            # Naive baseline: spread quantity evenly over first bucket of task window.
            if bucket.index == opt_input.time_buckets[0].index:
                for item, qty in task.quantity_requirements.items():
                    key = (item, task.site_id, bucket.index)
                    demand[key] = demand.get(key, 0.0) + float(qty)
    return DemandForecast(demand_by_item_site_bucket=demand)


def forecast_productivity(opt_input: OptimizationInput) -> ProductivityForecast:
    """
    Stub productivity / cycle-time forecast.

    For now, use a constant duration per task. Later, plug in a real
    regression model using inventory level and site features.
    """
    duration: Dict[str, int] = {}
    for task in opt_input.tasks:
        # Example: each task takes 1 time bucket in the baseline.
        duration[task.id] = 1
    return ProductivityForecast(duration_by_task_bucket=duration)

