from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from backend.database import init_db
from backend.routers import loans, transactions, rates, projections, users
from backend.services.scheduler import start_scheduler, stop_scheduler, daily_job


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    # Sync rates and bring every loan's balances up to today. Without this, balances
    # stay frozen at the last day the server was running until the nightly job fires.
    await daily_job()
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
static_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "static"))
if os.path.isdir(static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

    @app.get("/{path:path}")
    async def serve_frontend(path: str):
        # Unknown API routes should be a real 404, not the SPA's index.html
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        # Resolve the requested path and refuse anything that escapes static_dir
        # (e.g. "/..%2fdata%2floan_tracker.db" would otherwise serve the database).
        file_path = os.path.realpath(os.path.join(static_dir, path))
        is_inside_static_dir = file_path.startswith(static_dir + os.sep)
        if is_inside_static_dir and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(static_dir, "index.html"))
