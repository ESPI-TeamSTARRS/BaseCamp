from fastapi import FastAPI

from app.health.presentation.router import router as health_router


def create_app() -> FastAPI:
    application = FastAPI(title="basecamp-shop")
    application.include_router(health_router)
    return application


app = create_app()
