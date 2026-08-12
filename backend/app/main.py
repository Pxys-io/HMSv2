import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alembic import command
from alembic.config import Config
from app.api.public import auth as public_auth
from app.api.public import booking as public_booking
from app.api.public import profiles as public_profiles
from app.api.routes import (
    appointments,
    bulk,
    chat,
    csrf,
    custom_fields,
    dashboard,
    doctors,
    duplicates,
    expenses,
    files,
    financial,
    hr,
    icd10,
    inventory,
    labs,
    medications,
    notifications,
    ops,
    patients,
    printing,
    queue,
    scheduling,
    shared_docs,
    tags,
    tasks,
    users,
)
from app.api.routes import (
    audit as audit_router,
)
from app.api.routes import auth as staff_auth
from app.api.routes import (
    roles as roles_router,
)
from app.api.routes import settings as settings_router
from app.api.routes import visits as visits_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.middleware import RequestIDMiddleware
from app.services.outbox import outbox_loop
from app.services.reminder_jobs import reminder_loop


def _migrate_to_head() -> None:
    """Applies pending Alembic migrations on boot so a stale DB never 500s
    with missing tables (Plan/14 live-deploy hardening)."""
    backend = Path(__file__).resolve().parent.parent
    for ini in ("alembic.ini", "alembic_audit.ini"):
        cfg = Config(str(backend / ini))
        command.upgrade(cfg, "head")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _migrate_to_head()
    stop = asyncio.Event()
    worker = asyncio.create_task(outbox_loop(stop))
    reminder = asyncio.create_task(reminder_loop(stop))
    try:
        yield
    finally:
        stop.set()
        for task in (worker, reminder):
            try:
                await asyncio.wait_for(task, timeout=5)
            except TimeoutError:
                task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="HMSv2 API", version="0.1.0", lifespan=_lifespan)

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_error_handlers(app)

    @app.get("/")
    async def root():
        return {"message": "HMSv2 API is running"}

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "0.1.0", "env": settings.APP_ENV}

    app.include_router(staff_auth.router)
    app.include_router(public_auth.router)
    app.include_router(csrf.router)
    app.include_router(users.router)
    app.include_router(doctors.router)
    app.include_router(scheduling.router)
    app.include_router(appointments.router)
    app.include_router(patients.router)
    app.include_router(public_booking.router)
    app.include_router(public_profiles.router)
    app.include_router(queue.router)
    app.include_router(queue.display_router)
    app.include_router(visits_router.router)
    app.include_router(medications.router)
    app.include_router(files.router)
    app.include_router(financial.router)
    app.include_router(icd10.router)
    app.include_router(inventory.router)
    app.include_router(hr.router)
    app.include_router(labs.router)
    app.include_router(printing.router)
    app.include_router(chat.staff_router)
    app.include_router(chat.public_router)
    app.include_router(notifications.router)
    app.include_router(audit_router.router)
    app.include_router(bulk.router)
    app.include_router(settings_router.router)
    app.include_router(expenses.router)
    app.include_router(dashboard.router)
    app.include_router(duplicates.router)
    app.include_router(settings_router.public_router)
    app.include_router(shared_docs.router)
    app.include_router(roles_router.router)
    app.include_router(custom_fields.router)
    app.include_router(tags.router)
    app.include_router(tasks.router)
    app.include_router(ops.router)

    return app


app = create_app()
