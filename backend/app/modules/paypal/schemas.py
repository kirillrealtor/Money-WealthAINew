from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str = Field(min_length=1, max_length=127)
    amount: Decimal = Field(gt=0, le=99999999, max_digits=10, decimal_places=2)


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_id: UUID
    acknowledge: bool
