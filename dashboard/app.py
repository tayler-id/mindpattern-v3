"""FastAPI dashboard app factory — Research Agent Dashboard."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from fastapi.staticfiles import StaticFiles

from dashboard.routes import (
    api, editors_desk, engagement_history, findings, metrics, newsletters,
    performance, pipeline_status, prompts, run_history, skills,
    social_history, sse, traces,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="Research Agent Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mindpattern.fly.dev"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_credentials=True,
    allow_headers=["Authorization", "Content-Type"],
)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.include_router(editors_desk.router)
app.include_router(pipeline_status.router)
app.include_router(run_history.router)
app.include_router(prompts.router)
app.include_router(traces.router)
app.include_router(metrics.router)
app.include_router(performance.router)
app.include_router(findings.router)
app.include_router(newsletters.router)
app.include_router(skills.router)
app.include_router(social_history.router)
app.include_router(engagement_history.router)
app.include_router(sse.router)
app.include_router(api.router)

# Serve data directory for art images
DATA_DIR = Path(__file__).parent.parent / "data"
if DATA_DIR.exists():
    app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Serve the full dashboard page with Pipeline Status as the default tab."""
    ctx = pipeline_status.get_pipeline_context()
    return templates.TemplateResponse("base.html", {
        "request": request,
        "active_tab": "pipeline-status",
        **ctx,
    })
