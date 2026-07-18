"""
Sandbox runner — tries Docker first, falls back to in-process validation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import Any

from sandbox.validator import validate_story as _inprocess_validate


DOCKER_IMAGE = os.environ.get("SANDBOX_DOCKER_IMAGE", "python:3.11-slim")
USE_DOCKER = os.environ.get("SANDBOX_USE_DOCKER", "false").lower() == "true"


def run_in_docker(story_json: str) -> dict[str, Any]:
    """
    Spin up a throwaway Docker container, pipe the story JSON into
    sandbox/validator.py, and parse the result.
    """
    validator_path = os.path.join(os.path.dirname(__file__), "validator.py")

    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(open(validator_path, encoding="utf-8").read())
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "--network", "none",
                "--memory", "128m",
                "--cpus", "0.5",
                "-i",
                "-v", f"{tmp_path}:/validator.py:ro",
                DOCKER_IMAGE,
                "python", "/validator.py",
            ],
            input=story_json,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode not in (0, 1):
            raise RuntimeError(f"Docker exited {result.returncode}: {result.stderr}")
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, RuntimeError) as exc:
        raise RuntimeError(f"Docker sandbox failed: {exc}") from exc
    finally:
        os.unlink(tmp_path)


def validate_story(story: dict[str, Any]) -> dict[str, Any]:
    """
    Public entry point for SandboxValidatorAgent.
    Tries Docker if USE_DOCKER=true, otherwise runs in-process.
    """
    if USE_DOCKER:
        try:
            story_json = json.dumps(story)
            return run_in_docker(story_json)
        except Exception as exc:
            # Log and fall back to in-process
            print(f"[sandbox] Docker run failed ({exc}), using in-process fallback.", file=sys.stderr)

    return _inprocess_validate(story)
