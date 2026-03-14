from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from backend.database import init_db
from backend.routers import loans, transactions, rates, projections, users
from backend.services.scheduler import start_scheduler, stop_scheduler
from backend.services.rate_fetcher import fetch_and_store_rate


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    await fetch_and_store_rate()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(title="Loan Tracker", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(loans.router)
app.include_router(transactions.router)
app.include_router(rates.router)
app.include_router(projections.router)

# Serve frontend static files
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

    @app.get("/{path:path}")
    async def serve_frontend(path: str):
        file_path = os.path.join(static_dir, path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(static_dir, "index.html"))
