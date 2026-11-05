"""FastAPI application factory + lifecycle."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import close_pool, init_pool
from app.errors import register_exception_handlers
from app.logging_conf import configure_logging, logger
from app.middleware import HealthExemptTrustedHostMiddleware, SecurityMiddleware, TracingMiddleware
from app.modules.admin.router import router as admin_router
from app.modules.advisor.router import router as advisor_router
from app.modules.auth.router import router as auth_router
from app.modules.billing.router import router as billing_router
from app.modules.billing.router import webhook_router as billing_webhook_router
from app.modules.budgets.router import router as budgets_router
from app.modules.debt.router import router as debt_router
from app.modules.goals.router import router as goals_router
from app.modules.health.router import router as health_router
from app.modules.notifications.router import router as notifications_router
from app.modules.paypal.router import router as paypal_router
from app.modules.plaid.router import router as plaid_router
from app.modules.plaid.router import webhook_router as plaid_webhook_router
from app.modules.portfolio.router import router as portfolio_router
from app.modules.transactions.router import router as transactions_router
from app.redis_client import close_redis


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    import asyncio

    configure_logging()
    await init_pool()
    logger.info("server starting", service="api", port=settings.port, env=settings.env)

    # Optional in-process sync worker for single-node/dev. Production runs a
    # dedicated fleet (`python -m scripts.worker`) and leaves this off so the
    # web tier never does background work.
    worker_stop: asyncio.Event | None = None
    worker_task: asyncio.Task[None] | None = None
    if settings.sync_worker_enabled:
        from app.modules.plaid.worker import run_worker_loop

        worker_stop = asyncio.Event()
        worker_task = asyncio.create_task(run_worker_loop(stop=worker_stop))

    try:
        yield
    finally:
        if worker_stop is not None and worker_task is not None:
            worker_stop.set()
            await worker_task
        await close_pool()
        await close_redis()
        logger.info("server stopped", service="api")


def create_app() -> FastAPI:
    app = FastAPI(title="AI Financial Advisor API", version="1.0.0", lifespan=lifespan)

    # NOTE: Starlette applies middleware in reverse add order, so the LAST added
    # runs FIRST. Order below means: Tracing (outermost) -> Security -> CORS ->
    # TrustedHost -> handler.
    app.add_middleware(HealthExemptTrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,  # empty = no cross-origin
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type", "x-tenant-id", "x-trace-id"],
    )
    app.add_middleware(SecurityMiddleware)
    # Pure-ASGI tracing wraps everything so trace_id is set before handlers run.
    app.add_middleware(TracingMiddleware)

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(plaid_router)
    app.include_router(plaid_webhook_router)
    app.include_router(advisor_router)
    app.include_router(budgets_router)
    app.include_router(goals_router)
    app.include_router(debt_router)
    app.include_router(portfolio_router)
    app.include_router(paypal_router)
    app.include_router(transactions_router)
    app.include_router(notifications_router)
    app.include_router(admin_router)
    app.include_router(billing_router)
    app.include_router(billing_webhook_router)
    return app


app = create_app()
