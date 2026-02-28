from __future__ import annotations

import uuid
from typing import Dict, Tuple

from ortools.sat.python import cp_model

from domain.models import (
    Alert,
    AlertSeverity,
    AssignmentReason,
    Costs,
    OptimizationInput,
    OptimizationObjectiveBreakdown,
    OptimizationResult,
    Panel,
    PanelAssignment,
    PurchaseOrder,
)
from services.forecast import DemandForecast, ProductivityForecast, forecast_demand, forecast_productivity


def _build_model(
    opt_input: OptimizationInput,
    demand: DemandForecast,
    productivity: ProductivityForecast,
) -> tuple[cp_model.CpModel, Dict[Tuple[str, str, int], cp_model.IntVar]]:
    model = cp_model.CpModel()

    panels: Dict[str, Panel] = {p.id: p for p in opt_input.inventory.panels}

    x: Dict[Tuple[str, str, int], cp_model.IntVar] = {}
    for panel in panels.values():
        for site in opt_input.sites:
            for bucket in opt_input.time_buckets:
                var = model.NewBoolVar(f"x_{panel.id}_{site.id}_{bucket.index}")
                x[(panel.id, site.id, bucket.index)] = var

    for panel in panels.values():
        for bucket in opt_input.time_buckets:
            model.Add(
                sum(x[(panel.id, site.id, bucket.index)] for site in opt_input.sites) <= 1
            )

    for panel in panels.values():
        for site in opt_input.sites:
            for bucket in opt_input.time_buckets:
                if bucket.start < panel.available_from:
                    model.Add(x[(panel.id, site.id, bucket.index)] == 0)

    for site in opt_input.sites:
        for bucket in opt_input.time_buckets:
            for task in [t for t in opt_input.tasks if t.site_id == site.id]:
                if not (task.start_window <= bucket.start <= (task.end_window or bucket.end)):
                    continue
                for item, qty in task.quantity_requirements.items():
                    compatible_panels = [
                        p
                        for p in panels.values()
                        if item in p.compatible_forms and p.reuse_count < p.reuse_max
                    ]
                    if not compatible_panels:
                        continue
                    model.Add(
                        sum(
                            x[(panel.id, site.id, bucket.index)]
                            for panel in compatible_panels
                        )
                        >= qty
                    )

    purchase_cost = 0
    transfer_cost = 0
    handling_cost = 0
    labor_cost = 0
    delay_penalty = 0
    risk_penalty = 0

    model.Minimize(
        purchase_cost
        + transfer_cost
        + handling_cost
        + labor_cost
        + delay_penalty
        + risk_penalty
    )

    return model, x


def _solve(
    model: cp_model.CpModel,
    x: Dict[Tuple[str, str, int], cp_model.IntVar],
    opt_input: OptimizationInput,
) -> OptimizationResult:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)

    alerts: list[Alert] = []
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        alerts.append(
            Alert(
                code="NO_FEASIBLE_SOLUTION",
                message="Optimizer could not find a feasible assignment under current constraints.",
                severity=AlertSeverity.CRITICAL,
            )
        )

    assignments: list[PanelAssignment] = []
    for (panel_id, site_id, bucket_idx), var in x.items():
        if solver.Value(var) == 1:
            assignments.append(
                PanelAssignment(
                    panel_id=panel_id,
                    site_id=site_id,
                    time_bucket=bucket_idx,
                    reason_codes=[AssignmentReason.AVAILABLE],
                    transferred_from_site=None,
                )
            )

    objective = OptimizationObjectiveBreakdown(
        purchase_cost=0.0,
        transfer_cost=0.0,
        handling_cost=0.0,
        labor_cost=0.0,
        delay_penalty=0.0,
        risk_penalty=0.0,
        total_cost=float(solver.ObjectiveValue()) if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else 0.0,
    )

    return OptimizationResult(
        run_id=str(uuid.uuid4()),
        assignments=assignments,
        purchase_orders=[],
        alerts=alerts,
        objective=objective,
        completion_time_bucket=None,
    )


def optimize(opt_input: OptimizationInput) -> OptimizationResult:
    """
    Public entry-point: forecast -> optimize -> summarize.
    """
    demand = forecast_demand(opt_input)
    productivity = forecast_productivity(opt_input)
    model, x = _build_model(opt_input, demand, productivity)
    return _solve(model, x, opt_input)

