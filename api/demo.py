from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel, Field

FormType = Literal["SLAB", "COLUMN", "BEAM", "WALL"]
PanelCondition = Literal["OK", "DAMAGED", "REPAIRABLE"]
Mode = Literal["LOW_COST", "BALANCED", "FAST"]


class Panel(BaseModel):
    id: str
    panel_type: str
    size_m: list[float]
    compatible_forms: list[FormType]
    reuse_max: int
    reuse_count: int
    condition: PanelCondition
    available_from_day: int
    current_site: str


class Site(BaseModel):
    id: str
    name: str
    priority: int = Field(ge=1, le=5)
    deadline_day: int = Field(ge=1)
    storage_capacity_panels: int = Field(ge=50)
    location: dict[str, float]


class Task(BaseModel):
    id: str
    site_id: str
    form_type: FormType
    earliest_start_day: int
    latest_start_day: int
    duration_days: int
    requirements: dict[str, int]
    geometry_signature: str


class Costs(BaseModel):
    purchase: dict[str, float]
    transfer_cost_per_km: float
    delay_cost_per_day: float
    labor_cost_per_day: float


class Overrides(BaseModel):
    mode: Mode = "BALANCED"
    safety_stock_panels: int = 10
    deadline_override_day: int | None = None
    lock_assignments: list[dict[str, Any]] = Field(default_factory=list)


class DemoInput(BaseModel):
    start_date: str
    horizon_days: int
    sites: list[Site]
    inventory: list[Panel]
    tasks: list[Task]
    costs: Costs
    overrides: Overrides


class OptimizationResult(BaseModel):
    mode: Mode
    optimal_inventory_panels: int
    completion_time_days: int
    baseline_time_days: int
    purchase_cost: float
    transfer_cost: float
    delay_cost: float
    total_cost: float
    cost_saving_percent: float
    alerts: list[str] = Field(default_factory=list)


class ExplainResponse(BaseModel):
    one_liner: str
    bullets: list[str]
    technical_highlights: list[str]


@dataclass(frozen=True)
class ItemCatalogRow:
    key: str
    panel_type: str
    size_m: tuple[float, float]
    compatible: tuple[FormType, ...]


CATALOG: list[ItemCatalogRow] = [
    ItemCatalogRow("ALU_DECK_1x1", "ALU_DECK", (1.0, 1.0), ("SLAB",)),
    ItemCatalogRow("ALU_DECK_0.5x1", "ALU_DECK", (0.5, 1.0), ("SLAB",)),
    ItemCatalogRow("ALU_WALL_1x2", "ALU_WALL", (1.0, 2.0), ("WALL", "COLUMN")),
    ItemCatalogRow("ALU_WALL_0.5x2", "ALU_WALL", (0.5, 2.0), ("WALL", "COLUMN")),
    ItemCatalogRow("ALU_BEAM_0.3x2", "ALU_BEAM", (0.3, 2.0), ("BEAM",)),
]


def _dist_km(a: dict[str, float], b: dict[str, float]) -> float:
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def generate_demo_input(
    *,
    seed: int = 7,
    horizon_days: int = 90,
    n_sites: int = 3,
    n_panels: int = 420,
    n_tasks: int = 60,
    mode: Mode = "BALANCED",
) -> DemoInput:
    rng = random.Random(seed)
    start = date.today()

    sites: list[Site] = []
    for i in range(n_sites):
        sites.append(
            Site(
                id=f"S{i+1}",
                name=f"Site {chr(65+i)}",
                priority=rng.randint(1, 5),
                deadline_day=rng.randint(int(horizon_days * 0.6), horizon_days),
                storage_capacity_panels=rng.randint(120, 240),
                location={"x": rng.uniform(0, 50), "y": rng.uniform(0, 50)},
            )
        )

    inventory: list[Panel] = []
    damaged_rate = rng.uniform(0.02, 0.06)
    repairable_rate = rng.uniform(0.01, 0.03)

    for idx in range(n_panels):
        cat = rng.choice(CATALOG)
        reuse_max = rng.randint(150, 250)
        reuse_count = max(0, int(rng.gauss(mu=reuse_max * 0.35, sigma=reuse_max * 0.2)))
        reuse_count = min(reuse_count, reuse_max + rng.randint(0, 25))

        roll = rng.random()
        if roll < damaged_rate:
            condition: PanelCondition = "DAMAGED"
        elif roll < damaged_rate + repairable_rate:
            condition = "REPAIRABLE"
        else:
            condition = "OK"

        site = rng.choice(sites).id
        available_from_day = max(0, int(rng.gauss(mu=3, sigma=4)))
        available_from_day = min(available_from_day, 20)

        inventory.append(
            Panel(
                id=f"P{idx+1:04d}",
                panel_type=cat.panel_type,
                size_m=[cat.size_m[0], cat.size_m[1]],
                compatible_forms=list(cat.compatible),
                reuse_max=reuse_max,
                reuse_count=reuse_count,
                condition=condition,
                available_from_day=available_from_day,
                current_site=site,
            )
        )

    def make_requirements(ft: FormType) -> dict[str, int]:
        if ft == "SLAB":
            return {
                "ALU_DECK_1x1": rng.randint(60, 140),
                "ALU_DECK_0.5x1": rng.randint(20, 80),
                "PROP": rng.randint(60, 140),
                "BEAM": rng.randint(15, 40),
            }
        if ft == "COLUMN":
            return {
                "ALU_WALL_1x2": rng.randint(20, 70),
                "ALU_WALL_0.5x2": rng.randint(10, 50),
                "TIE_ROD": rng.randint(20, 80),
                "CLAMP": rng.randint(40, 120),
            }
        if ft == "WALL":
            return {
                "ALU_WALL_1x2": rng.randint(40, 120),
                "ALU_WALL_0.5x2": rng.randint(20, 90),
                "TIE_ROD": rng.randint(40, 140),
                "CLAMP": rng.randint(60, 200),
            }
        return {
            "ALU_BEAM_0.3x2": rng.randint(20, 70),
            "PROP": rng.randint(30, 90),
            "CLAMP": rng.randint(20, 80),
        }

    def task_duration(ft: FormType) -> int:
        if ft == "SLAB":
            return rng.randint(4, 8)
        if ft == "COLUMN":
            return rng.randint(2, 5)
        if ft == "WALL":
            return rng.randint(3, 7)
        return rng.randint(3, 6)

    tasks: list[Task] = []
    for t in range(n_tasks):
        ft: FormType = rng.choices(
            ["SLAB", "COLUMN", "BEAM", "WALL"],
            weights=[0.45, 0.2, 0.15, 0.2],
            k=1,
        )[0]

        site = rng.choice(sites)
        earliest = rng.randint(0, max(1, horizon_days - 15))
        latest = min(horizon_days - 1, earliest + rng.randint(3, 14))
        dur = task_duration(ft)

        tasks.append(
            Task(
                id=f"T{t+1:03d}",
                site_id=site.id,
                form_type=ft,
                earliest_start_day=earliest,
                latest_start_day=latest,
                duration_days=dur,
                requirements=make_requirements(ft),
                geometry_signature=f"{ft}-G{rng.randint(1,10)}",
            )
        )

    costs = Costs(
        purchase={
            "ALU_DECK_1x1": 85.0,
            "ALU_DECK_0.5x1": 55.0,
            "ALU_WALL_1x2": 120.0,
            "ALU_WALL_0.5x2": 85.0,
            "ALU_BEAM_0.3x2": 95.0,
            "PROP": 40.0,
            "BEAM": 60.0,
            "TIE_ROD": 12.0,
            "CLAMP": 4.0,
        },
        transfer_cost_per_km=1.2,
        delay_cost_per_day=3500.0,
        labor_cost_per_day=1800.0,
    )

    overrides = Overrides(
        mode=mode,
        safety_stock_panels=10 if mode == "BALANCED" else (18 if mode == "FAST" else 6),
        deadline_override_day=None,
        lock_assignments=[],
    )

    return DemoInput(
        start_date=start.isoformat(),
        horizon_days=horizon_days,
        sites=sites,
        inventory=inventory,
        tasks=tasks,
        costs=costs,
        overrides=overrides,
    )


def explain_result(res: OptimizationResult) -> ExplainResponse:
    one_liner = (
        "We auto-allocate real inventory to kits and schedules, then optimize purchase + transfers "
        "to minimize total cost including delay penalties—while enforcing reuse-life and site constraints."
    )

    bullets = [
        f"Mode: {res.mode} — optimizer selects {res.optimal_inventory_panels} panels as the best time–cost trade-off.",
        f"Completion: {res.completion_time_days} days vs baseline {res.baseline_time_days} days (schedule + reuse-cycle aware).",
        f"Total cost: ₹{res.total_cost:,.0f} including purchase, transfers, labor, and delay penalties.",
        f"Estimated savings: {res.cost_saving_percent:.1f}% driven by inventory-first assignment and reduced idle/over-ordering.",
        "Hard constraints enforced: panel availability dates, transport lead times, reuse/stripping cycles, and safety stock.",
        "Last-minute issue handling: shortages/conflicts trigger transfer or buy suggestions instead of silent failure.",
    ]

    technical = [
        "Constraint-based scheduling: prevents double-booking the same panel across sites/time windows.",
        "Lifecycle-aware allocation: blocks near-failure or damaged panels unless explicitly overridden.",
        "Total-cost objective: purchase + logistics + labor + delay penalties ⇒ true optimal BoQ, not theoretical maxima.",
    ]

    if res.alerts:
        bullets.append(f"Active alerts: {len(res.alerts)} (e.g., {res.alerts[0]})")

    return ExplainResponse(one_liner=one_liner, bullets=bullets, technical_highlights=technical)


router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/generate-demo", response_model=DemoInput)
def generate_demo(
    seed: int = 7,
    horizon_days: int = 90,
    n_sites: int = 3,
    n_panels: int = 420,
    n_tasks: int = 60,
    mode: Mode = "BALANCED",
    save_to_disk: bool = False,
) -> DemoInput:
    demo = generate_demo_input(
        seed=seed,
        horizon_days=horizon_days,
        n_sites=n_sites,
        n_panels=n_panels,
        n_tasks=n_tasks,
        mode=mode,
    )

    if save_to_disk:
        with open("demo_input.json", "w", encoding="utf-8") as f:
            f.write(demo.model_dump_json(indent=2))

    return demo


@router.post("/import")
async def import_data(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    name = file.filename or "uploaded"
    size = len(content)

    parsed: str
    try:
        json.loads(content.decode("utf-8"))
        parsed = "json"
    except Exception:
        parsed = "not_json"

    return {"status": "received", "filename": name, "bytes": size, "detected": parsed}


@router.post("/explain", response_model=ExplainResponse)
def explain(res: OptimizationResult) -> ExplainResponse:
    return explain_result(res)

