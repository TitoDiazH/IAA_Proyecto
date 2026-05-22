from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers import courses, reports, uploads
from app.services.analysis_queue import start_analysis_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_analysis_worker()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uploads.router)
app.include_router(courses.router)
app.include_router(reports.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
