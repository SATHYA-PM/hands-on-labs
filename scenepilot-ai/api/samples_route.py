"""
Demo library route — serves the seeded sample story files.

GET /samples           → list available samples
GET /samples/{name}    → return the full story JSON
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["samples"])

SAMPLES_DIR = Path(__file__).parent.parent / "data" / "samples"


@router.get("/samples")
def list_samples():
    files = sorted(SAMPLES_DIR.glob("*.json"))
    return {
        "samples": [
            {
                "name": f.stem,
                "filename": f.name,
                "url": f"/api/samples/{f.stem}",
            }
            for f in files
        ]
    }


@router.get("/samples/{name}")
def get_sample(name: str):
    # Guard against path traversal
    safe_name = Path(name).name
    path = SAMPLES_DIR / f"{safe_name}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Sample '{name}' not found.")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data
