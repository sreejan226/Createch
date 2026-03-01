from __future__ import annotations

import uuid
from datetime import date
from typing import Dict, List, Tuple

from ortools.sat.python import cp_model

from domain.models import (
    Alert,
    AlertSeverity,
    AssignmentReason,
    OptimizationInput,
    OptimizationObjectiveBreakdown,
    OptimizationResult,
    Panel,
    PanelAssignment,
    PurchaseOrder,
    TimeBucket,
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

    # Placeholder objective: minimize number of assigned panels.
    # In a fuller version this becomes:
    # purchase_cost + transfer_cost + handling_cost + labor_cost + delay_penalty + risk_penalty
    model.Minimize(
        sum(x_var for x_var in x.values())
    )

    return model, x


def _compute_purchase_orders(opt_input: OptimizationInput) -> List[PurchaseOrder]:
    """Compute simple, time-aware purchase orders based on task demand vs consumables.

    For each material:
    - Sum total required quantity across all tasks.
    - Subtract available consumables from the inventory snapshot.
    - If there is a deficit, create a PurchaseOrder with:
      - quantity = deficit
      - arrival_bucket = earliest time bucket where that material is first needed.
    """
    required_by_item: Dict[str, int] = {}
    earliest_use_date: Dict[str, TimeBucket] = {}

    buckets: List[TimeBucket] = opt_input.time_buckets
    if not buckets:
        return []
    first_bucket_start = buckets[0].start

    def _bucket_for_date(d: date) -> int:
        delta_days = (d - first_bucket_start).days
        idx = max(0, delta_days)
        return min(idx, buckets[-1].index)

    for task in opt_input.tasks:
        for item, qty in task.quantity_requirements.items():
            required_by_item[item] = required_by_item.get(item, 0) + qty
            use_bucket_idx = _bucket_for_date(task.start_window)
            if item not in earliest_use_date or use_bucket_idx < earliest_use_date[item].index:
                earliest_use_date[item] = TimeBucket(
                    index=use_bucket_idx,
                    start=first_bucket_start + (task.start_window - first_bucket_start),
                    end=first_bucket_start + (task.start_window - first_bucket_start),
                )

    available = dict(opt_input.inventory.consumables)

    purchase_orders: List[PurchaseOrder] = []
    for item, required in required_by_item.items():
        avail = available.get(item, 0)
        deficit = max(0, required - avail)
        if deficit <= 0:
            continue
        bucket = earliest_use_date.get(item)
        arrival_bucket = bucket.index if bucket is not None else 0
        purchase_orders.append(
            PurchaseOrder(item=item, quantity=deficit, arrival_bucket=arrival_bucket)
        )

    return purchase_orders


def compute_purchase_orders(opt_input: OptimizationInput) -> List[PurchaseOrder]:
    """
    Compute time-aware purchase orders from task demand minus current consumables.
    Use this for BoQ generation so the API returns quickly without running the full CP-SAT optimizer.
    """
    return _compute_purchase_orders(opt_input)


def _solve(
    model: cp_model.CpModel,
    x: Dict[Tuple[str, str, int], cp_model.IntVar],
    opt_input: OptimizationInput,
) -> OptimizationResult:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)

    alerts: List[Alert] = []
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        alerts.append(
            Alert(
                code="NO_FEASIBLE_SOLUTION",
                message="Optimizer could not find a feasible assignment under current constraints.",
                severity=AlertSeverity.CRITICAL,
            )
        )

    assignments: List[PanelAssignment] = []
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

    purchase_orders = _compute_purchase_orders(opt_input)

    # --- Cost breakdown (simple but meaningful) ---
    costs = opt_input.costs

    # 1) Purchase cost: sum of unit_price * quantity for each purchase order.
    purchase_cost = sum(
        po.quantity * costs.purchase.get(po.item, 0.0) for po in purchase_orders
    )

    # 2) Labor cost: assume each task consumes ~1 day of labor (stub).
    labor_cost = len(opt_input.tasks) * costs.labor_per_day

    # 3) Delay penalty: compare latest task end per site vs (possibly overridden) site deadline.
    latest_end_by_site: Dict[str, date] = {}
    for task in opt_input.tasks:
        d = task.end_window or task.start_window
        prev = latest_end_by_site.get(task.site_id)
        if prev is None or d > prev:
            latest_end_by_site[task.site_id] = d

    delay_penalty = 0.0
    for site in opt_input.sites:
        override_deadline = opt_input.overrides.deadline_override.get(site.id)
        effective_deadline = override_deadline or site.deadline
        site_end = latest_end_by_site.get(site.id, effective_deadline)
        lateness_days = max(0, (site_end - effective_deadline).days)
        delay_penalty += lateness_days * costs.delay_per_day

    # 4) Handling and transfer & risk costs: left as 0.0 for now (placeholders).
    handling_cost = 0.0
    transfer_cost = 0.0
    risk_penalty = 0.0

    total_cost = (
        purchase_cost + transfer_cost + handling_cost + labor_cost + delay_penalty + risk_penalty
    )

    objective = OptimizationObjectiveBreakdown(
        purchase_cost=purchase_cost,
        transfer_cost=transfer_cost,
        handling_cost=handling_cost,
        labor_cost=labor_cost,
        delay_penalty=delay_penalty,
        risk_penalty=risk_penalty,
        total_cost=total_cost,
    )

    return OptimizationResult(
        run_id=str(uuid.uuid4()),
        assignments=assignments,
        purchase_orders=purchase_orders,
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

