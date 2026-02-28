from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional, Sequence

from pydantic import BaseModel, Field


class PanelCondition(str, Enum):
    GOOD = "GOOD"
    WORN = "WORN"
    DAMAGED = "DAMAGED"


class Mode(str, Enum):
    LOW_COST = "LOW_COST"
    BALANCED = "BALANCED"
    FAST = "FAST"


class Panel(BaseModel):
    id: str
    type: str
    size: str
    compatible_forms: Sequence[str] = Field(default_factory=list)
    reuse_max: int
    reuse_count: int = 0
    condition: PanelCondition = PanelCondition.GOOD
    available_from: date
    home_site: Optional[str] = None


class Site(BaseModel):
    id: str
    location: str
    priority: int = 1
    deadline: date
    handling_cost: float = 0.0
    storage_capacity: Optional[int] = None


class Task(BaseModel):
    id: str
    site_id: str
    form_type: str  # slab / column / beam / wall
    start_window: date
    end_window: Optional[date] = None
    quantity_requirements: Dict[str, int]  # item -> quantity
    geometry_signature: Optional[str] = None


class InventorySnapshot(BaseModel):
    as_of: datetime
    panels: List[Panel] = Field(default_factory=list)
    consumables: Dict[str, int] = Field(default_factory=dict)


class Costs(BaseModel):
    purchase: Dict[str, float] = Field(default_factory=dict)  # item -> unit cost
    transfer_per_km: float
    delay_per_day: float
    labor_per_day: float


class Overrides(BaseModel):
    deadline_override: Dict[str, date] = Field(default_factory=dict)  # site_id -> deadline
    safety_stock_override: Dict[str, int] = Field(default_factory=dict)  # item -> min qty
    lock_assignments: Dict[str, str] = Field(
        default_factory=dict
    )  # panel_id -> site_id (locked)
    mode: Mode = Mode.BALANCED


class TimeBucket(BaseModel):
    index: int
    start: date
    end: date


class OptimizationInput(BaseModel):
    time_buckets: List[TimeBucket]
    sites: List[Site]
    tasks: List[Task]
    inventory: InventorySnapshot
    costs: Costs
    overrides: Overrides = Field(default_factory=Overrides)


class AssignmentReason(str, Enum):
    AVAILABLE = "AVAILABLE"
    COMPATIBLE = "COMPATIBLE"
    REUSE_OK = "REUSE_OK"
    TRANSFER_OPTIMAL = "TRANSFER_OPTIMAL"
    OVERRIDE_LOCKED = "OVERRIDE_LOCKED"


class PanelAssignment(BaseModel):
    panel_id: str
    site_id: str
    time_bucket: int
    reason_codes: List[AssignmentReason]
    transferred_from_site: Optional[str] = None


class PurchaseOrder(BaseModel):
    item: str
    quantity: int
    arrival_bucket: int


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Alert(BaseModel):
    code: str
    message: str
    severity: AlertSeverity


class OptimizationObjectiveBreakdown(BaseModel):
    purchase_cost: float
    transfer_cost: float
    handling_cost: float
    labor_cost: float
    delay_penalty: float
    risk_penalty: float
    total_cost: float


class OptimizationResult(BaseModel):
    run_id: str
    assignments: List[PanelAssignment]
    purchase_orders: List[PurchaseOrder]
    alerts: List[Alert]
    objective: OptimizationObjectiveBreakdown
    completion_time_bucket: Optional[int] = None

