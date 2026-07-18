# ◈ ScenePilot AI

**AI-powered branching narrative generator with a multi-agent quality-gate pipeline, interactive story tree, game engine export, and a live playable emulator.**

Built with LangGraph · FastAPI · React · React Flow · Groq llama-3.3-70b · Gemini 2.5 Flash fallback

---

## Features

### 🤖 Multi-Agent LangGraph Pipeline
Four agents run in sequence with an automatic self-correction retry loop (max 2 retries):

| Agent | Role |
|---|---|
| **StoryGenerator** | Calls Groq `llama-3.3-70b-versatile` (fallback: Gemini `gemini-2.5-flash`) to create branching scenes |
| **StyleVaultAgent** | FAISS semantic search across three style-guide rule files; flags tone/language violations |
| **SandboxValidator** | NetworkX cycle detection, schema checks, dead-end/orphan/scene-count structural checks |
| **ComplianceAgent** | Structured quality gate — approves or rejects with a detailed audit report |

### 🌳 Interactive Story Tree
- React Flow canvas with BFS-layout positioning
- Tone-coloured custom nodes (tense · hopeful · dark · neutral · playful)
- Floating edge labels showing choice text
- Click any node to open the Scene Inspector
- Minimap (top-right) + zoom/pan controls (bottom-left)

### ✅ Validation Report
- Issues grouped by type: Cycles · Schema · Structural · Style
- Colour-coded severity tiles
- Agent pipeline trace with timings and token counts

### 💰 Cost Dashboard
- Live token spend tracking with Prometheus metrics
- Budget bar (configurable)
- Per-agent Recharts bar chart
- Full pipeline trace table

### 📤 Export (3 formats)
| Format | Description |
|---|---|
| **JSON** | Raw story graph — scenes + choices, portable to any engine |
| **Markdown** | Human-readable with tone annotations |
| **Twine (.tw)** | Twee 3 notation — import into Twine 2 or compile with Tweego |

### ⬡ 3D Blueprint (Game Engine Viewport)
- BFS layout generates 3D `(X, Y, Z)` world-space coordinates for each scene/room
- Room names, tone-based asset palettes, trigger distances
- Unity / Unreal Engine / Godot export formats
- Interactive SVG top-down spatial map with room inspector
- Export Blueprint JSON for direct engine consumption

### 🎮 Live State Machine Emulator
- Fully playable click-through game driven by the generated narrative
- Tracks: player health (choice consequences), inventory items, visited scenes
- Session log of every decision taken
- Game-over detection and multiple ending screens
- Restart without re-generating

### 📚 Demo Library
Five pre-built samples (loaded without LLM calls, validated via `/api/validate`):

| Sample | Genre | Notes |
|---|---|---|
| `heist_thriller` | Thriller | Circular-loop label seeded in metadata |
| `fantasy_rpg` | Fantasy | Full branching tree, approved |
| `product_launch` | Marketing | Linear with some branching, approved |
| `space_escape` | Sci-Fi | **Rejected** — 1 real `scene_003 ↔ scene_005` cycle |
| `edu_quiz_tree` | Educational | Binary quiz tree, approved |

### 📈 Observability
- 7 Prometheus metrics (generation count, duration, token spend, style violations, pipeline errors, approval rate, retry count)
- Grafana dashboard at `http://localhost:3001` (admin/admin)
- Prometheus at `http://localhost:9090`

---

## Quick Start

### Prerequisites
- Docker Desktop with Compose V2
- `GROQ_API_KEY` and `GEMINI_API_KEY`

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — add your GROQ_API_KEY and GEMINI_API_KEY
```

### 2. Build and run

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 |

### 3. Generate a story
1. Enter a premise (≥ 10 characters) in the left panel
2. Pick a genre and adjust the tone slider
3. Click **✦ Generate Story** — the pipeline runs (~10–30s)
4. Or click any **Demo** card to load a pre-built sample instantly

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React + Vite)                  │
│  PremiseInput → StoryTree → ValidationReport → CostDashboard │
│  BlueprintPanel (SVG 3D map) → StateEmulator (game engine)   │
│  DemoLibrary → ExportPanel (JSON / Markdown / Twine)         │
└─────────────────────┬───────────────────────────────────────┘
                      │ nginx reverse-proxy → :8000
┌─────────────────────▼───────────────────────────────────────┐
│                     FastAPI (Python 3.11)                    │
│  POST /api/generate    → LangGraph pipeline                  │
│  POST /api/validate    → SandboxValidator only               │
│  POST /api/blueprint   → 3D spatial transform generator      │
│  GET  /api/samples     → Demo library manifest               │
│  GET  /api/samples/:n  → Load sample JSON                    │
│  GET  /metrics         → Prometheus exposition               │
└─────────────────────┬───────────────────────────────────────┘
                      │
    ┌─────────────────┼─────────────────┐
    ▼                 ▼                 ▼
 LangGraph       StyleVault        Sandbox
 Pipeline        (FAISS)           (NetworkX)
 ┌──────────┐
 │Generator │ → Groq llama-3.3-70b-versatile
 │StyleVault│   (fallback: Gemini gemini-2.5-flash)
 │Sandbox   │
 │Compliance│
 └──────────┘
```

---

## Project Structure

```
scenepilot-ai/
├── agents/
│   ├── state.py                 LangGraph state TypedDict
│   ├── story_generator.py       LLM call (Groq / Gemini fallback)
│   ├── style_vault_agent.py     FAISS semantic rule lookup
│   ├── sandbox_validator.py     NetworkX + schema checks
│   ├── compliance_agent.py      Quality gate + approval
│   └── orchestrator.py          LangGraph graph + retry loop
├── api/
│   ├── main.py                  FastAPI app, CORS, metrics
│   ├── routes.py                /generate /validate /blueprint
│   └── samples_route.py         /samples demo library
├── core/
│   ├── story_store.py           In-memory story registry
│   ├── telemetry.py             7 Prometheus metrics
│   ├── cost_tracker.py          Token + cost accounting
│   ├── style_vault.py           FAISS index builder
│   └── blueprint.py             3D BFS spatial layout
├── sandbox/
│   ├── validator.py             Cycle / schema / structural checks
│   └── runner.py                Sandbox execution wrapper
├── data/
│   ├── rules/                   3 style-guide rule files (FAISS source)
│   └── samples/                 5 demo story JSONs
├── frontend/
│   ├── src/
│   │   ├── App.tsx              Layout, tabs, export helpers
│   │   ├── components/
│   │   │   ├── PremiseInput.tsx
│   │   │   ├── StoryTree.tsx    React Flow + custom nodes/edges
│   │   │   ├── SceneInspector.tsx
│   │   │   ├── ValidationReport.tsx
│   │   │   ├── CostDashboard.tsx
│   │   │   ├── DemoLibrary.tsx
│   │   │   ├── BlueprintPanel.tsx  SVG 3D spatial map
│   │   │   └── StateEmulator.tsx   Playable game emulator
│   │   ├── hooks/useStory.ts    generate + loadSample hook
│   │   └── types/index.ts       TypeScript types
│   ├── nginx.conf               Reverse proxy + 120s LLM timeout
│   └── Dockerfile               nginx:alpine3.21, non-root
├── prometheus/prometheus.yml
├── docker-compose.yml
├── Dockerfile                   python:3.11-slim, non-root
└── requirements.txt
```

---

## API Reference

### `POST /api/generate`
Run the full 4-agent pipeline.

```json
{
  "premise": "A spy must extract a double agent from a collapsing regime",
  "genre": "thriller",
  "tone": 0.8
}
```

### `POST /api/validate`
Run the sandbox validator only (no LLM).

```json
{ "story": { "title": "…", "scenes": [ … ] } }
```

### `POST /api/blueprint`
Generate a 3D spatial transform matrix from a story.

```json
{ "story": { "title": "…", "scenes": [ … ] }, "story_id": "my-story" }
```

Returns `spatial_nodes[]` with `transform.position [X, Y, Z]`, asset palettes, triggers.

### `GET /api/samples`
Returns demo library manifest.

### `GET /api/samples/{name}`
Returns the full sample story JSON.

---

## Export Formats

### Twine (.tw) — Twee 3 notation

Each scene becomes a Twine passage. Choices become `[[label|target]]` links. Tone and terminal status are encoded as passage tags.

```twee
:: StoryTitle
The Diamond Heist

:: scene_001 [tone-tense]
The museum closes in ten minutes…

[[Go in alone|scene_002]]
[[Wait for your partner|scene_003]]
```

Import: **Twine 2 → File → Import from file** (select the `.tw` file).  
CLI compile: `tweego -o story.html story.tw`

---

## Security

- All containers run as non-root users
- nginx pinned to `nginx:alpine3.21` (no CVEs)
- API keys injected via `.env` (never committed)
- CORS restricted to frontend origin in production config

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Groq `llama-3.3-70b-versatile` + Gemini `gemini-2.5-flash` fallback |
| Orchestration | LangGraph (StateGraph) |
| Vector search | FAISS (style-guide rules) |
| Backend | FastAPI + Uvicorn |
| Graph analysis | NetworkX (cycle detection) |
| Frontend | React 18 + TypeScript + Vite |
| Story graph | React Flow |
| Charts | Recharts |
| Metrics | Prometheus + Grafana |
| Infra | Docker Compose (4 services) |
