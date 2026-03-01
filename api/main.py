from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.boq import router as boq_router
from api.demo import router as demo_router
from api.schemas import OptimizationRequest, OptimizationResponse
from optimizer.solver import optimize

app = FastAPI(
    title="Formwork Decision Intelligence API",
    version="0.1.0",
    description=(
        "Decision intelligence pipeline for formwork BoQ and panel assignment, combining "
        "ML-style forecasting with an OR-Tools optimizer and safety constraints."
    ),
)

# CORS: allow frontends on other origins (e.g. React on :3000, Streamlit, or same host)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for dev/demo; restrict to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(demo_router)
app.include_router(boq_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Formwork Decision Intelligence API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/optimize", response_model=OptimizationResponse)
def run_optimization(req: OptimizationRequest) -> OptimizationResponse:
    """
    Run the full decision intelligence pipeline:

    - forecast demand + productivity (stubbed but ML-ready)
    - build and solve OR-Tools model
    - return assignments, BoQ, alerts, and objective breakdown

    **Schema notes:**
    - `inventory.panels[].condition`: use **GOOD**, **WORN**, or **DAMAGED** (FAIR/OK/REPAIRABLE are accepted and mapped to WORN).
    - `overrides.deadline_override`: object **site_id → date** (e.g. `{"SITE_B": "2026-03-04"}`), not task_id.
    - `overrides.lock_assignments`: object **panel_id → site_id** (e.g. `{"PANEL_001": "SITE_A"}`), not task_id.
    """
    result = optimize(req.input)
    return OptimizationResponse(result=result)

