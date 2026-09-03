from __future__ import annotations

import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from ipaddress import ip_address

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from tabletop_companion.api.combat_routes import register_combat_routes
from tabletop_companion.api.errors import register_error_handlers
from tabletop_companion.api.local_routes import register_local_routes
from tabletop_companion.api.routes import register_routes
from tabletop_companion.api.runtime import EventHub, SafeErrorLog, SlidingWindowRateLimiter
from tabletop_companion.application.combat_service import CombatService
from tabletop_companion.application.local_service import LocalMultiplayerService
from tabletop_companion.application.service import CompanionService
from tabletop_companion.config import Settings
from tabletop_companion.domain.rules import DEFAULT_RULESET, CardSampler
from tabletop_companion.infrastructure.database import (
    create_database_engine,
    create_session_factory,
)
from tabletop_companion.infrastructure.migrations import run_migrations
from tabletop_companion.infrastructure.security import (
    Argon2RoomPasswordHasher,
    HmacSecretDigester,
    load_or_create_host_secret,
)
from tabletop_companion.infrastructure.uow import SqlAlchemyUnitOfWorkFactory
from tabletop_companion.logging_config import configure_logging


def _is_host_client(host: str) -> bool:
    if host in {"localhost", "testclient"}:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def create_app(
    settings: Settings | None = None,
    *,
    sampler: CardSampler | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    configure_logging(resolved_settings.log_level)
    engine = create_database_engine(resolved_settings.database_url)
    session_factory = create_session_factory(engine)
    uow_factory = SqlAlchemyUnitOfWorkFactory(session_factory)
    random_source = secrets.SystemRandom()
    service = CompanionService(
        uow_factory=uow_factory,
        rulesets={DEFAULT_RULESET.version: DEFAULT_RULESET},
        sampler=sampler or random_source.sample,
    )
    digester = HmacSecretDigester(load_or_create_host_secret(resolved_settings.host_secret_path))
    local_service = LocalMultiplayerService(
        uow_factory=uow_factory,
        ruleset=DEFAULT_RULESET,
        digester=digester,
        password_hasher=Argon2RoomPasswordHasher(),
    )
    combat_service = CombatService(uow_factory=uow_factory, randint=random_source.randint)
    hub = EventHub(
        room_limit=resolved_settings.websocket_room_limit,
        device_limit=resolved_settings.websocket_device_limit,
        queue_size=resolved_settings.websocket_queue_size,
        projector=combat_service.project_event,
    )
    limiter = SlidingWindowRateLimiter()
    safe_errors = SafeErrorLog()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        del application
        run_migrations(resolved_settings.database_url)
        yield
        engine.dispose()

    app = FastAPI(
        title="Tabletop Companion Local Host",
        version="0.2.0-alpha.1",
        lifespan=lifespan,
        description=(
            "Offline-first LAN API. Use /api/v2 for authenticated local multiplayer; "
            "the compatibility /api/v1 surface is restricted to the host device."
        ),
    )

    @app.middleware("http")
    async def restrict_legacy_api(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        client_host = request.client.host if request.client else ""
        if request.url.path.startswith("/api/v1/") and not _is_host_client(client_host):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "permission_denied",
                        "message": "The compatibility API is available only on the host device.",
                        "details": {},
                    }
                },
            )
        return await call_next(request)

    register_error_handlers(app, safe_errors)
    register_routes(app, service)
    register_combat_routes(app, combat_service, hub)
    register_local_routes(
        app,
        local_service,
        service,
        hub,
        limiter,
        resolved_settings,
        time.monotonic(),
        safe_errors,
        combat_service,
    )
    app.state.local_service = local_service
    app.state.event_hub = hub
    app.state.settings = resolved_settings
    app.state.safe_errors = safe_errors
    if resolved_settings.frontend_dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=resolved_settings.frontend_dist, html=True),
            name="frontend",
        )
    return app
