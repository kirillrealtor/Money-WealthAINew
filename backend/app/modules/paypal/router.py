from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from app.config import settings
from app.deps import CurrentUser, rate_limit, require_verified

from . import service
from .schemas import AssessmentRequest, OrderRequest

router = APIRouter(prefix="/api/v1/paypal", tags=["paypal"],
                   dependencies=[Depends(rate_limit("paypal", 10))])


@router.get("/config")
async def config(user: CurrentUser = Depends(require_verified)) -> dict[str, bool]:
    return {"configured": bool(settings.paypal_client_id and settings.paypal_client_secret), "sandbox": True}


@router.post("/assess")
async def assess(body: AssessmentRequest, user: CurrentUser = Depends(require_verified)) -> dict[str, Any]:
    return await service.assess(user.user_id, user.tenant_id, body)


@router.post("/orders")
async def create(body: OrderRequest, user: CurrentUser = Depends(require_verified)) -> dict[str, Any]:
    return await service.create_order(user.user_id, user.tenant_id, str(body.purchase_id), body.acknowledge)


@router.get("/purchases/{purchase_id}")
async def get(purchase_id: UUID, user: CurrentUser = Depends(require_verified)) -> dict[str, Any]:
    return await service.get_purchase(user.user_id, user.tenant_id, str(purchase_id))


@router.post("/purchases/{purchase_id}/capture")
async def capture(purchase_id: UUID, user: CurrentUser = Depends(require_verified)) -> dict[str, Any]:
    return await service.capture_order(user.user_id, user.tenant_id, str(purchase_id))
