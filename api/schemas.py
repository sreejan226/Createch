from __future__ import annotations

from pydantic import BaseModel

from domain.models import OptimizationInput, OptimizationResult


class OptimizationRequest(BaseModel):
    input: OptimizationInput


class OptimizationResponse(BaseModel):
    result: OptimizationResult

