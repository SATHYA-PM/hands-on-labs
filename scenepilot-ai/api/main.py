"""
FastAPI application entrypoint.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from core.telemetry import setup_otel
from api.routes import router as story_router
from api.samples_route import router as samples_router

setup_otel()

app = FastAPI(
    title="ScenePilot AI",
    version="1.0.0",
    description="AI-powered branching narrative generator with quality-gate pipeline.",
)

# ── CORS (allow Vite dev server + Vercel deploy) ─────────────────────────────
origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(story_router)
app.include_router(samples_router)


# ── Prometheus metrics endpoint ──────────────────────────────────────────────
# Exposed as a plain GET route (not a sub-app mount) so Prometheus scrapes
# /metrics directly without a 307 redirect to /metrics/.
@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health():
    return {"status": "ok", "service": "scenepilot-ai"}
