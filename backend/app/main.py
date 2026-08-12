import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.public import auth as public_auth
from app.api.public import booking as public_booking
from app.api.public import profiles as public_profiles
from app.api.routes import (
    appointments,
    chat,
    csrf,
    doctors,
    files,
    financial,
    medications,
    notifications,
    patients,
    printing,
    queue,
    scheduling,
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


@asynccontextmanager
async def _lifespan(app: FastAPI):
    stop = asyncio.Event()
    worker = asyncio.create_task(outbox_loop(stop))
    try:
        yield
    finally:
        stop.set()
        try:
            await asyncio.wait_for(worker, timeout=5)
        except TimeoutError:
            worker.cancel()


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
    app.include_router(printing.router)
    app.include_router(chat.staff_router)
    app.include_router(chat.public_router)
    app.include_router(notifications.router)
    app.include_router(audit_router.router)
    app.include_router(settings_router.router)
    app.include_router(settings_router.public_router)
    app.include_router(roles_router.router)

    return app


app = create_app()
