# ◈ ScenePilot AI

**AI-powered branching narrative generator with a multi-agent quality-gate pipeline, diff-patch self-healing, token budget gates, interactive story tree, game engine export, and a live playable emulator.**

Built with LangGraph · FastAPI · React · React Flow · Groq llama-3.3-70b · Gemini 2.5 Flash fallback

---

## What is ScenePilot AI?

ScenePilot AI takes a story premise, genre, and tone and produces a fully validated branching narrative graph — structurally correct, style-compliant, and ready for export to JSON, Markdown, Twine, or a 3D game engine blueprint.

The pipeline is self-healing: if the first generation contains graph cycles, it does **not** regenerate the entire story. It identifies the exact broken edges, sends a ~600-token targeted repair patch to the LLM, merges the patch into the original story, and re-validates — cutting retry token spend by over 80%.

---

## Features

### 🤖 Multi-Agent LangGraph Pipeline

Four agents run in sequence with an automatic self-correction retry loop (configurable, default 3 retries):

| Agent | Role |
|---|---|
| **StoryGeneratorAgent** | Calls Groq `llama-3.3-70b-versatile` (fallback: Gemini `gemini-2.5-flash`) to create branching scenes. On retry, switches to REPAIR MODE — sends only the broken scenes and a patch prompt |
| **StyleVaultAgent** | FAISS semantic search across three style-guide rule files; flags tone/language violations |
| **SandboxValidatorAgent** | NetworkX cycle detection (with exact `invalid_edges` extraction), schema checks, dead-end/orphan/scene-count structural checks |
| **ComplianceAgent** | Structured quality gate — approves or rejects with a SHA-256 fingerprinted audit report |

### ⚙️ Diff-Patch Self-Healing (Repair Mode)

On retry attempt ≥ 1, when `broken_nodes` are present in state:

1. The sandbox extracts the exact `(source_id, target_id)` edge pairs that form cycles
2. The generator sends **only** those scenes + the validator's issue list to the LLM (`max_tokens=1024`)
3. The LLM returns a minimal patch object: `{ "scene_id": [new_choices] }`
4. `core/utils.merge_patch()` deep-merges the patch into the original story — all valid scenes preserved
5. `_break_cycles()` runs as a safety net before re-validation

| Pass | Prompt type | Typical tokens |
|---|---|---|
| Attempt 1 | Full generation | ~9,000 |
| Attempt 2+ | Repair patch only | ~600 |

### 🛡️ Three-Layer Token Budget Gate

| Layer | Where | What it does |
|---|---|---|
| **Pre-flight** | `api/routes.py` | Estimates worst-case cost (`full_gen + 1,200 × MAX_RETRIES`) before any LLM call; rejects with a concrete `TOKEN_BUDGET_LIMIT=N` recommendation |
| **Router gate** | `agents/orchestrator.py` | `_has_budget_for_retry()` checks remaining balance against mode-aware reserve (1,200 repair / 9,500 full-gen) before allowing each retry |
| **Generator guard** | `agents/story_generator.py` | Defence-in-depth: refuses the LLM call if balance < reserve; surfaces `last_story` as best-effort result instead of `None` |

### 🌳 Interactive Story Tree
- React Flow canvas with BFS-layout positioning
- Tone-coloured custom nodes (tense · hopeful · dark · neutral · playful)
- Floating edge labels showing choice text
- Click any node to open the Scene Inspector
- Minimap + zoom/pan controls

### ✅ Validation Report
- Issues grouped by type: Cycles · Schema · Structural · Style
- Colour-coded severity tiles
- Budget-gate aware status banners (`BUDGET HALT` / `PRE-FLIGHT REJECTED` / `BUDGET EXHAUSTED`)
- Agent pipeline trace with per-span token counts, ceiling, and `repair` badge

### 💰 Cost Dashboard
- Live token spend with budget bar (turns red on halt)
- Repair Passes card — shown when diff-patch retries fired
- Budget-halt warning banner with config fix link
- Pipeline Trace table: `Tokens Used` (cumulative) + `Ceiling` columns
- Per-agent Recharts bar chart — repair and halt spans coloured distinctly

### 🎮 Live State Machine Emulator
- Fully playable click-through game driven by the generated narrative
- Tracks: player health (choice consequences), inventory items, visited scenes
- Session log of every decision taken
- Partial-story warning banner when token budget was exhausted mid-generation
- Game-over detection and multiple ending screens

### 📤 Export (3 formats)

| Format | Description |
|---|---|
| **JSON** | Raw story graph — scenes + choices, portable to any engine |
| **Markdown** | Human-readable with tone annotations |
| **Twine (.tw)** | Twee 3 notation — import into Twine 2 or compile with Tweego |

### ⬡ 3D Blueprint (Game Engine Viewport)
- BFS layout generates 3D `(X, Y, Z)` world-space coordinates per scene/room
- Room names, tone-based asset palettes, trigger distances
- Unity / Unreal Engine / Godot export formats
- Interactive SVG top-down spatial map with room inspector

### 📚 Demo Library
Five pre-built samples (loaded without LLM calls, validated via `/api/validate`):

| Sample | Genre | Notes |
|---|---|---|
| `heist_thriller` | Thriller | Circular-loop label seeded in metadata |
| `fantasy_rpg` | Fantasy | Full branching tree, approved |
| `product_launch` | Marketing | Linear with branching, approved |
| `space_escape` | Sci-Fi | **Rejected** — real `scene_003 ↔ scene_005` cycle |
| `edu_quiz_tree` | Educational | Binary quiz tree, approved |

### 📈 Observability
- Prometheus metrics: generation count, validation duration, token spend, style violations, sandbox rejections, budget halts, loop detections
- Grafana dashboard at `http://localhost:3001`
- Prometheus at `http://localhost:9090`

---

## Quick Start

### Prerequisites
- Docker Desktop with Compose V2
- `GROQ_API_KEY` and `GEMINI_API_KEY`

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in your API keys and review token budget settings
```

Key settings in `.env`:

```env
GROQ_API_KEY=your_key
GEMINI_API_KEY=your_key

TOKEN_BUDGET_LIMIT=20000   # raise for complex premises (see table below)
MAX_RETRIES=3
SCENE_MULTIPLIER=40        # output multiplier for pre-flight estimate (lower for edu/marketing)
```

**Recommended `TOKEN_BUDGET_LIMIT` by premise complexity:**

| Premise size | Recommended ceiling |
|---|---|
| Short (< 100 chars) | 5,000 |
| Standard (100–300 chars) | 10,000 |
| Complex (300–700 chars) | 20,000 |
| Very complex (700+ chars, 50+ scenes) | 30,000+ |

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
    ┌─────────────────┼──────────────────────┐
    ▼                 ▼                      ▼
 LangGraph        StyleVault            Sandbox
 Pipeline         (FAISS)               (NetworkX)
 ┌────────────────────────────────────┐
 │ generate → style_vault → sandbox  │
 │     ↓ (fail)                      │
 │ _has_budget_for_retry()?          │
 │     ↓ yes          ↓ no           │
 │   retry           fail            │
 │     ↓                             │
 │ repair_mode?                      │
 │   yes → patch prompt (~600 tok)   │
 │   no  → full prompt (~9,000 tok)  │
 └────────────────────────────────────┘
```

---

## Project Structure

```
scenepilot-ai/
├── agents/
│   ├── state.py                 LangGraph state TypedDict (incl. broken_nodes, last_story, budget_halt)
│   ├── story_generator.py       Full-gen + REPAIR MODE + budget guard
│   ├── style_vault_agent.py     FAISS semantic rule lookup
│   ├── sandbox_validator.py     NetworkX cycle detection with invalid_edges extraction
│   ├── compliance_agent.py      Quality gate + SHA-256 audit
│   └── orchestrator.py         LangGraph graph + budget-aware retry router
├── api/
│   ├── main.py                  FastAPI app, CORS, metrics
│   ├── routes.py                /generate (pre-flight estimator) /validate /blueprint
│   └── samples_route.py         /samples demo library
├── core/
│   ├── story_store.py           In-memory story registry
│   ├── telemetry.py             Prometheus metrics
│   ├── cost_tracker.py          Token budget enforcement class
│   ├── style_vault.py           FAISS index builder
│   ├── blueprint.py             3D BFS spatial layout
│   └── utils.py                 merge_patch() — deep-merges repair patches into story
├── sandbox/
│   ├── validator.py             Cycle / schema / structural checks + invalid_edges
│   └── runner.py                Docker sandbox execution wrapper
├── data/
│   ├── rules/                   3 style-guide rule files (FAISS source)
│   └── samples/                 5 demo story JSONs
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── PremiseInput.tsx
│   │   │   ├── StoryTree.tsx        React Flow + custom nodes/edges
│   │   │   ├── SceneInspector.tsx
│   │   │   ├── ValidationReport.tsx  Budget-halt aware banners + repair badge
│   │   │   ├── CostDashboard.tsx     Repair/halt span colours + budget-halt card
│   │   │   ├── DemoLibrary.tsx
│   │   │   ├── BlueprintPanel.tsx    SVG 3D spatial map
│   │   │   └── StateEmulator.tsx     Playable emulator + partial-story warning
│   │   ├── hooks/useStory.ts
│   │   └── types/index.ts            AgentSpan (tokens_used, token_ceiling, repair_mode) + MIN_SCENES
│   ├── nginx.conf
│   └── Dockerfile
├── prometheus/prometheus.yml
├── .gitattributes               LF line-ending policy
├── .gitignore
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## API Reference

### `POST /api/generate`
Run the full 4-agent pipeline with pre-flight budget estimation.

```json
{
  "premise": "A spy must extract a double agent from a collapsing regime",
  "genre": "thriller",
  "tone": 0.8
}
```

**Response includes:**
- `token_spend` — actual tokens consumed across all agents
- `token_ceiling` — the active `TOKEN_BUDGET_LIMIT`
- `agent_spans[]` — per-agent trace with `tokens_used`, `token_ceiling`, `repair_mode`, `cycles`
- `validation.cycles_detected` — number of graph cycles found
- `error` — prefixed with `PRE-FLIGHT REJECTED`, `BUDGET HALT`, or `BUDGET EXHAUSTED` for precise client handling

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

### `GET /api/samples` / `GET /api/samples/{name}`
Demo library manifest and individual sample JSON.

---

## Export Formats

### Twine (.tw) — Twee 3 notation

```twee
:: StoryTitle
The Diamond Heist

:: scene_001 [tone-tense]
The museum closes in ten minutes…

[[Go in alone|scene_002]]
[[Wait for your partner|scene_003]]
```

Import: **Twine 2 → File → Import from file**
CLI compile: `tweego -o story.html story.tw`

---

## Security

- All containers run as non-root users
- nginx pinned to `nginx:alpine3.21`
- API keys injected via `.env` (never committed — gitignored)
- CORS restricted to frontend origin
- `.gitattributes` enforces LF line endings repo-wide

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Groq `llama-3.3-70b-versatile` + Gemini `gemini-2.5-flash` fallback |
| Orchestration | LangGraph (StateGraph) |
| Diff-patch repair | `core/utils.merge_patch()` + targeted repair prompt |
| Token budget gates | Pre-flight estimator · Router gate · Generator guard |
| Vector search | FAISS (style-guide rules) |
| Backend | FastAPI + Uvicorn |
| Graph analysis | NetworkX (cycle detection + `invalid_edges` extraction) |
| Frontend | React 18 + TypeScript + Vite |
| Story graph | React Flow |
| Charts | Recharts |
| Metrics | Prometheus + Grafana |
| Infra | Docker Compose (4 services) |
| AI Engineering Assistant | IBM Bob (architecture, diff-patch repair, budget gates, observability) |