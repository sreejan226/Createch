"""
Convert demo (API) format to domain format for the optimizer.
Used so BoQ can run the optimizer with demo data + Excel consumables.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Dict

from domain.models import (
    Costs,
    InventorySnapshot,
    Mode as DomainMode,
    OptimizationInput,
    Overrides,
    Panel,
    PanelCondition,
    Site,
    Task,
    TimeBucket,
)

if TYPE_CHECKING:
    from api.demo import DemoInput  # avoid circular import at runtime


def _parse_start_date(start_date_str: str) -> date:
    return datetime.strptime(start_date_str, "%Y-%m-%d").date()


def _demo_panel_condition_to_domain(condition: str) -> PanelCondition:
    c = (condition or "").upper()
    if c == "DAMAGED":
        return PanelCondition.DAMAGED
    if c in ("WORN", "REPAIRABLE"):
        return PanelCondition.WORN
    return PanelCondition.GOOD


def demo_to_optimization_input(demo: "DemoInput", consumables: Dict[str, int]) -> OptimizationInput:
    """Build OptimizationInput from DemoInput and consumables (e.g. from Excel inventory)."""
    start = _parse_start_date(demo.start_date)
    horizon_days = demo.horizon_days

    time_buckets = [
        TimeBucket(
            index=i,
            start=start + timedelta(days=i),
            end=start + timedelta(days=i),
        )
        for i in range(horizon_days)
    ]

    sites = [
        Site(
            id=s.id,
            location=s.name,
            priority=s.priority,
            deadline=start + timedelta(days=s.deadline_day),
            storage_capacity=s.storage_capacity_panels,
        )
        for s in demo.sites
    ]

    tasks = [
        Task(
            id=t.id,
            site_id=t.site_id,
            form_type=t.form_type,
            start_window=start + timedelta(days=t.earliest_start_day),
            end_window=start + timedelta(days=t.latest_start_day),
            quantity_requirements=dict(t.requirements),
            geometry_signature=t.geometry_signature,
        )
        for t in demo.tasks
    ]

    mode_str = (demo.overrides.mode or "BALANCED").upper()
    domain_mode = DomainMode.BALANCED
    if mode_str == "LOW_COST":
        domain_mode = DomainMode.LOW_COST
    elif mode_str == "FAST":
        domain_mode = DomainMode.FAST

    panels = [
        Panel(
            id=p.id,
            type=p.panel_type,
            size="x".join(str(x) for x in p.size_m),
            compatible_forms=list(p.compatible_forms),
            reuse_max=p.reuse_max,
            reuse_count=p.reuse_count,
            condition=_demo_panel_condition_to_domain(p.condition),
            available_from=start + timedelta(days=p.available_from_day),
            home_site=p.current_site,
        )
        for p in demo.inventory
    ]

    inventory = InventorySnapshot(
        as_of=datetime.now(),
        panels=panels,
        consumables=consumables,
    )

    costs = Costs(
        purchase=dict(demo.costs.purchase),
        transfer_per_km=demo.costs.transfer_cost_per_km,
        delay_per_day=demo.costs.delay_cost_per_day,
        labor_per_day=demo.costs.labor_cost_per_day,
    )

    overrides = Overrides(mode=domain_mode)

    return OptimizationInput(
        time_buckets=time_buckets,
        sites=sites,
        tasks=tasks,
        inventory=inventory,
        costs=costs,
        overrides=overrides,
    )

