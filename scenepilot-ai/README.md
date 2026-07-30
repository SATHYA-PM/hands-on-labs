# ◈ ScenePilot AI

**AI-powered branching narrative generator with a multi-agent quality-gate pipeline, IBM Granite Guardian content safety, diff-patch self-healing, token budget gates, interactive story tree, game engine export, and a live playable emulator.**

> Built with **IBM Bob** (AI Engineering Assistant) · **IBM Granite Guardian 3-8b** · LangGraph · FastAPI · React · Groq llama-3.3-70b · Gemini 2.5 Flash

---

## 🤖 Built with IBM Bob

Every architectural decision, every bug fix, and every feature in this project was designed and implemented in collaboration with **IBM Bob** — IBM's AI software engineering assistant.

IBM Bob contributed:

| Contribution | Detail |
|---|---|
| **Architecture design** | Multi-agent LangGraph pipeline, repair mode priority chain, budget gate layers |
| **Diff-patch repair system** | Four specialised repair modes (cycle, schema, structural, style) — each saves >80% tokens vs full regeneration |
| **Schema sanitiser** | `_sanitise_schema()` — deterministic field repair at parse time, zero LLM calls |
| **Dangling ref fixer** | `_fix_dangling_refs()` — redirects 100+ broken `next` references in-process without LLM |
| **Genre-scoped FAISS rules** | 5 genre-specific style rule files + per-genre vault cache |
| **SSE live progress stream** | `core/progress.py` — per-run bounded queue, real-time stage messages in the UI |
| **Persistent story store** | Atomic JSON file writes with temp-rename pattern, survives server restarts |
| **LLM retry + backoff** | Per-provider exponential backoff before fallback chain escalation |
| **IBM Granite Guardian integration** | End-to-end watsonx.ai credential debugging, model selection, pipeline wiring |
| **Frontend improvements** | Per-scene FAISS score bars, precise rejection banners, live stage messages, story bar download button |
| **Debugging** | Guardian API key format, watsonx region mismatch, project ID resolution, model deprecation |

---

## 🛡️ IBM Granite Guardian — Content Safety Gate

ScenePilot AI integrates **IBM Granite Guardian 3-8b** via watsonx.ai as a mandatory content safety gate. Every generated story passes through Guardian before approval.

### What Guardian checks

| Risk Category | What it detects |
|---|---|
| `harm` | General harmful content |
| `violence` | Graphic violence descriptions |
| `hate` | Hate speech, discrimination |
| `sexual_content` | Explicit sexual content |
| `profanity` | Offensive language |

### How it works

```
Sandbox Validator → IBM Granite Guardian → Compliance
                         ↓
              Each scene checked across 5 categories
              Risk score: 0.0 (safe) → 1.0 (harmful)
              Threshold: 0.8 (configurable via GUARDIAN_THRESHOLD)
                         ↓
              score ≥ 0.8 → scene BLOCKED → story REJECTED
              score < 0.8 → scene PASSES → story proceeds
```

### Fail-safe design

- `GUARDIAN_ENABLED=false` → node passes through in 0ms, zero API calls
- If watsonx.ai is unreachable → logs warning span, **never crashes the pipeline**
- Only explicit `BLOCKED` verdicts revoke approval — API errors are non-blocking

### Configuration

```env
GUARDIAN_ENABLED=true
WATSONX_API_KEY=your_ibm_cloud_api_key
WATSONX_PROJECT_ID=your_watsonx_project_id
WATSONX_URL=https://us-south.ml.cloud.ibm.com
GUARDIAN_THRESHOLD=0.8
GUARDIAN_MODEL=ibm/granite-guardian-3-8b   # optional override
```

---

## ❌ Problems Before — ✅ Solutions After

### Problem 1 — Stories always REJECTED with "Max retries exceeded"

**Before:** The repair loop only had `cycle_repair` and `style_repair` modes. Orphaned scenes, dangling `next` references, and missing schema fields had **no repair path**. After 2 attempts the pipeline gave up regardless of story quality.

**After:** Four specialised repair modes, evaluated in priority order:

| Priority | Mode | Fixes | Token cost |
|---|---|---|---|
| 1 | **Cycle repair** | Graph back-edges forming loops | ~600 tokens |
| 2 | **Schema repair** | Missing `tone`, `text`, `choices` fields | ~400 tokens |
| 3 | **Structural repair** | Orphaned scenes, dangling `next` references | ~500 tokens |
| 4 | **Style repair** | Tone mismatches, style guideline violations | ~800 tokens |

Additionally, `_sanitise_schema()` and `_fix_dangling_refs()` run deterministically **at parse time** — fixing the most common issues (missing `tone` on last scene, `next` pointing to scene_NNN that was never written) in **0ms with zero LLM tokens**.

---

### Problem 2 — FAISS scoring 75+ false advisory warnings per run

**Before:** `STYLE_SIMILARITY_THRESHOLD=0.35` flagged virtually every scene. The advisory section was 75+ flat text lines — impossible to read, no numeric scores visible.

**After:**
- Threshold lowered to `0.20` — calibrated to prose vs sentence-level rules
- Advisory section replaced with a **per-scene score table**: scene ID · numeric score · colour-coded bar (🟢 ≥0.25 · 🟡 0.15–0.25 · 🔴 <0.15) · nearest rule
- Sorted worst-first so the most problematic scenes appear at top
- Typical run: 0–2 advisory warnings instead of 75+

---

### Problem 3 — FAISS rules were genre-agnostic (thriller checked against marketing rules)

**Before:** All three rule files loaded for every story regardless of genre. A thriller scene was compared against marketing copy rules — producing meaningless similarity scores.

**After:** Genre-specific rule subdirectories created for all 5 genres:

```
data/rules/
├── creative_writing_guidelines.txt    (common — all genres)
├── narrative_tone_standards.txt       (common — all genres)
├── story_schema_patterns.txt          (common — all genres)
├── thriller/genre_rules.txt           (tension, urgency, antagonist logic)
├── fantasy/genre_rules.txt            (world-building, magic consistency, hope arc)
├── sci-fi/genre_rules.txt             (tech grounding, systemic consequences)
├── educational/genre_rules.txt        (learning objectives, age-appropriate tone)
└── marketing/genre_rules.txt          (brand alignment, CTAs, Grade 8 language)
```

Per-genre FAISS vault cached on first use — subsequent runs are instant.

---

### Problem 4 — Stories lost on server restart (in-memory store)

**Before:** `story_store` was a Python dict. Every Docker container restart wiped all story history. `GET /api/stories/{id}` returned 404 after any restart.

**After:** Stories persisted as individual JSON files in `data/stories/`. Atomic write pattern (temp file → `os.replace`) prevents corruption on crash. Store scans directory on startup and rebuilds index — all previous stories survive restarts.

---

### Problem 5 — LLM quota errors caused immediate fallback (no retry)

**Before:** Any Groq 429 rate-limit immediately consumed the fallback provider quota. Groq rate limits are often transient (minute-window resets in 1–5 seconds).

**After:** Each provider gets **1 automatic retry** with exponential backoff (`LLM_RETRY_DELAY=2.0s` default) before the chain escalates to the next provider. Recovers most transient 429s without burning Gemini quota.

---

### Problem 6 — Static spinner with no pipeline visibility

**Before:** The UI showed "Generating branching narrative…" for the entire 30–120 second run. No indication of which stage was running, how many tokens remained, or which repair pass was executing.

**After:** Server-Sent Events (SSE) progress stream — `GET /api/progress/{story_id}` — emits live stage events from each agent node. The status bar shows:

```
Generating branching narrative…          · GENERATING
Checking style guidelines…               · STYLE-CHECK
Running sandbox validation…              · VALIDATING
Fixing 3 structural issue(s)…  (retry 1) · STRUCTURAL-REPAIR
IBM Granite Guardian scanning…           · GUARDIAN
Generating compliance fingerprint…       · COMPLIANCE
```

---

### Problem 7 — Rejection banner said "0 issues detected" (useless)

**Before:** When the story was rejected due to structural issues, the banner said `✗ Rejected — 0 issues detected` because FAISS advisory (non-blocking) was counted but structural warnings were not surfaced correctly.

**After:** Rejection banner names the exact causes:
```
✗ Rejected — 2 structural issue(s) (orphaned/dangling scenes), 1 schema error(s)
```

---

### Problem 8 — IBM Granite Guardian not connecting

**Before:** Three separate credential issues prevented Guardian from working:
1. API key stored with `ApiKey-` prefix — IBM IAM requires UUID only
2. Wrong watsonx region (`eu-de` instead of `us-south`)
3. Model `ibm/granite-guardian-3-2-2b` not available on Lite/free plan

**After:**
- API key stripped to UUID format: `zjB8hRSb...LUFj`
- URL corrected to `https://us-south.ml.cloud.ibm.com`
- Model switched to `ibm/granite-guardian-3-8b` (available on Lite, configurable via `GUARDIAN_MODEL` env var)
- Guardian now runs successfully: **31 scenes scanned · 0 violations · ✓ APPROVED**

---

## What is ScenePilot AI?

ScenePilot AI takes a story premise, genre, and tone and produces a fully validated, content-safe branching narrative graph — structurally correct, style-compliant, and ready for export to JSON, Markdown, Twine, or a 3D game engine blueprint.

---

## Features

### 🤖 Multi-Agent LangGraph Pipeline

Seven agents run in sequence with an automatic self-correction retry loop (configurable, default 2 retries):

| Agent | Role |
|---|---|
| **StoryGeneratorAgent** | Calls Groq `llama-3.3-70b-versatile` (fallback: `llama-3.1-8b-instant` → Gemini `gemini-2.5-flash`). On retry, activates one of four targeted repair modes |
| **HallucinationVerifierAgent** | RAG-style confidence + grounding check. Embeds each scene against premise fragments using `all-MiniLM-L6-v2`; flags scenes with low similarity (< 0.20) or novel entities absent from premise |
| **StyleVaultAgent** | FAISS semantic search across common + genre-specific rule files. Blocking: tone mismatches. Advisory: similarity scores shown as colour-coded bars |
| **SandboxValidatorAgent** | NetworkX cycle detection, JSON schema validation, orphan/dangling-ref structural checks |
| **GraniteGuardianAgent** | IBM Granite Guardian 3-8b content safety scan via watsonx.ai. Checks harm/violence/hate/sexual/profanity across all scenes |
| **ComplianceAgent** | SHA-256 fingerprinted audit report, persists story to disk |

### ⚙️ Four-Mode Diff-Patch Self-Healing

On retry, instead of regenerating the entire story (~9,000 tokens), the pipeline sends a targeted patch:

| Pass | Mode | Prompt size | Typical tokens |
|---|---|---|---|
| Attempt 1 | Full generation | All scenes | ~9,000 |
| Attempt 2 | Cycle repair | Only broken scenes + back-edges | ~600 |
| Attempt 2 | Schema repair | Only malformed scenes + error list | ~400 |
| Attempt 2 | Structural repair | Only orphaned/dangling scenes | ~500 |
| Attempt 2 | Style repair | Only failing scenes + violation report | ~800 |

**Zero-token pre-repair:** `_sanitise_schema()` fills missing fields and `_fix_dangling_refs()` redirects broken `next` references **before** sandbox validation — eliminating the most common LLM truncation errors without any LLM call.

### 🛡️ Three-Layer Token Budget Gate

| Layer | Where | What it does |
|---|---|---|
| **Pre-flight** | `api/routes.py` | Estimates worst-case cost before any LLM call; rejects with exact `TOKEN_BUDGET_LIMIT=N` recommendation |
| **Router gate** | `agents/orchestrator.py` | Checks remaining balance vs mode-aware reserve before each retry |
| **Generator guard** | `agents/story_generator.py` | Defence-in-depth: refuses LLM call if balance < reserve; surfaces `last_story` as best-effort |

### 📡 Live SSE Progress Stream

`GET /api/progress/{story_id}` — Server-Sent Events stream showing real-time pipeline stage, message, and retry count. Connected automatically when generation starts.

### 🌳 Interactive Story Tree
- React Flow canvas with BFS-layout positioning
- Tone-coloured nodes: tense (orange) · hopeful (green) · dark (black) · neutral (blue) · playful (purple)
- Floating choice labels on edges
- Click any node → Scene Inspector

### ✅ Validation Report
- Per-scene FAISS score table with colour-coded bars (green/amber/red)
- Precise rejection banner naming exact failure causes
- Agent pipeline trace with token counts and repair badges
- All 6 metric tiles: Cycles · Schema · Tone · Advisory · Structural · Tokens

### 💰 Cost Dashboard
- Token spend bar (budget ceiling 40,000)
- Per-agent duration bar chart — Guardian shown separately
- Pipeline trace: all agents with durations and status

### 🎮 Live State Machine Emulator
- Fully playable click-through game driven by the generated narrative
- Tracks vitality, threat level, inventory, visited scenes
- Session log of every decision
- Play Again button on story completion

### 📤 Export (3 formats + Quick Download)

| Format | Description |
|---|---|
| **↓ JSON** | Quick-access button on story bar — one click |
| **JSON** | Raw story graph — scenes + choices, portable to any engine |
| **Markdown** | Human-readable with tone annotations |
| **Twine (.tw)** | Twee 3 notation — import into Twine 2 or compile with Tweego |

### ⬡ 3D Blueprint (Game Engine Viewport)
- BFS layout generates 3D `(X, Y, Z)` world-space coordinates per scene/room
- Room names, tone-based asset palettes, trigger distances, world dimensions
- Unity (C# MonoBehaviour) / Unreal Engine (Blueprint JSON) / Godot (GDScript Resource) export
- Interactive SVG spatial map with room inspector

### 📚 Demo Library
Five pre-built samples loaded without LLM calls, validated via `/api/validate`:

| Sample | Genre | Notes |
|---|---|---|
| `heist_thriller` | Thriller | Master thief premise |
| `fantasy_rpg` | Fantasy | Full branching tree |
| `product_launch` | Marketing | Linear with branching |
| `space_escape` | Sci-Fi | Seeded cycle for demo |
| `edu_quiz_tree` | Educational | Binary quiz tree |

### 📈 Observability
- Prometheus metrics: generation count, validation duration, token spend, style violations, sandbox rejections, guardian blocks, loop detections
- Grafana dashboard: `http://localhost:3001` (password: `scenepilot`)
- Prometheus: `http://localhost:9090`

---

## Quick Start

### Prerequisites
- Docker Desktop with Compose V2
- `GROQ_API_KEY` (free at https://console.groq.com)
- `GEMINI_API_KEY` (free at https://aistudio.google.com)
- IBM Cloud API key + watsonx.ai Project ID (free at https://cloud.ibm.com) — optional, for Guardian

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in your API keys
```

Key settings:

```env
# LLM providers
GROQ_API_KEY=your_groq_key
GEMINI_API_KEY=your_gemini_key

# IBM Granite Guardian (optional — set false to disable)
GUARDIAN_ENABLED=true
WATSONX_API_KEY=your_ibm_cloud_api_key   # UUID only, no "ApiKey-" prefix
WATSONX_PROJECT_ID=your_project_id
WATSONX_URL=https://us-south.ml.cloud.ibm.com
GUARDIAN_THRESHOLD=0.8

# Pipeline tuning
TOKEN_BUDGET_LIMIT=40000   # raise for complex premises
MAX_RETRIES=2
STYLE_SIMILARITY_THRESHOLD=0.20
LLM_RETRY_DELAY=2.0        # seconds before retrying a 429
```

**Recommended `TOKEN_BUDGET_LIMIT` by premise complexity:**

| Premise size | Recommended ceiling |
|---|---|
| Short (< 100 chars) | 10,000 |
| Standard (100–300 chars) | 20,000 |
| Complex (300–700 chars) | 40,000 |
| Very complex (700+ chars) | 60,000 |

### 2. Build and run

```bash
docker compose build --no-cache
docker compose up
```

| Service | URL |
|---|---|
| **Frontend** | http://localhost:5173 |
| **API** | http://localhost:8000 |
| **API Docs** | http://localhost:8000/docs |
| **Prometheus** | http://localhost:9090 |
| **Grafana** | http://localhost:3001 |

### 3. Generate a story
1. Enter a premise (≥ 10 characters) in the left panel
2. Pick a genre and adjust the tone slider (Dark → Playful)
3. Click **✦ Generate Story** — watch the live progress bar
4. Or click any **Demo** card to load a pre-built sample instantly

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Frontend (React 18 + Vite)                 │
│  PremiseInput → StoryTree (React Flow) → ValidationReport    │
│  CostDashboard → BlueprintPanel (SVG) → StateEmulator        │
│  DemoLibrary → ExportPanel (JSON / Markdown / Twine)         │
│  useProgress hook → SSE /api/progress/{id} live stages       │
└──────────────────────┬───────────────────────────────────────┘
                       │ nginx reverse-proxy → :8000
┌──────────────────────▼───────────────────────────────────────┐
│                    FastAPI (Python 3.11)                      │
│  POST /api/generate        → LangGraph pipeline              │
│  GET  /api/progress/{id}   → SSE live stage stream           │
│  POST /api/validate        → SandboxValidator only           │
│  POST /api/blueprint       → 3D spatial transform            │
│  GET  /api/samples         → Demo library                    │
│  GET  /metrics             → Prometheus exposition           │
└──────────────────────┬───────────────────────────────────────┘
                       │
     ┌─────────────────┴──────────────────────────┐
     ▼                                             ▼
 LangGraph Pipeline                          core/progress.py
 ┌──────────────────────────────────────┐    (SSE event bus)
 │  generate                           │
 │      ↓                              │
 │  hallucination_verifier  ← NEW      │
 │      ↓                              │
 │  style_vault → sandbox              │
 │      ↓ fail                         │
 │  schema/structural/cycle repair?    │
 │      ↓                              │
 │  guardian (IBM Granite Guardian)    │
 │      ↓                              │
 │  compliance → END                   │
 └──────────────────────────────────────┘
     │              │              │
  LLM chain      FAISS          sentence-transformers
  (Groq+retry    (genre         (all-MiniLM-L6-v2)
  → Gemini)      rules)         + NetworkX
                                 + _sanitise_schema()
                                 + _fix_dangling_refs()
```

---

## Project Structure

```
scenepilot-ai/
├── agents/
│   ├── state.py                 LangGraph state TypedDict
│   ├── story_generator.py       Generation + 4 repair modes + schema sanitiser
│   ├── hallucination_verifier.py  RAG confidence + grounding check (NEW)
│   ├── style_vault_agent.py     Genre-scoped FAISS style check (blocking + advisory)
│   ├── sandbox_validator.py     NetworkX cycles + schema + structural checks
│   ├── granite_guardian.py      IBM Granite Guardian content safety gate
│   ├── compliance_agent.py      SHA-256 audit + disk persistence
│   └── orchestrator.py         LangGraph graph + budget-aware retry router + SSE
├── api/
│   ├── main.py                  FastAPI app, CORS, metrics mount
│   ├── routes.py                /generate (pre-flight) /progress /validate /blueprint
│   └── samples_route.py         /samples demo library
├── core/
│   ├── story_store.py           Atomic JSON file store (survives restarts)
│   ├── progress.py              Per-run SSE event queue (emit/stream/close)
│   ├── llm_client.py            3-provider fallback chain with retry + backoff
│   ├── style_vault.py           FAISS index builder (common + genre rules)
│   ├── telemetry.py             Prometheus metrics
│   ├── blueprint.py             3D BFS spatial layout
│   └── utils.py                 merge_patch() for diff-patch repair
├── sandbox/
│   └── validator.py             Cycle / schema / structural checks
├── data/
│   ├── rules/
│   │   ├── creative_writing_guidelines.txt
│   │   ├── narrative_tone_standards.txt
│   │   ├── story_schema_patterns.txt
│   │   ├── thriller/genre_rules.txt
│   │   ├── fantasy/genre_rules.txt
│   │   ├── sci-fi/genre_rules.txt
│   │   ├── educational/genre_rules.txt
│   │   └── marketing/genre_rules.txt
│   ├── samples/                 5 demo story JSONs
│   └── stories/                 Generated stories (persisted, gitignored)
├── frontend/
│   └── src/
│       ├── App.tsx
│       ├── components/
│       │   ├── PremiseInput.tsx
│       │   ├── StoryTree.tsx         React Flow + tone-coloured nodes
│       │   ├── SceneInspector.tsx
│       │   ├── ValidationReport.tsx  FAISS score bars + precise banners
│       │   ├── CostDashboard.tsx     Per-agent chart + budget bar
│       │   ├── DemoLibrary.tsx
│       │   ├── BlueprintPanel.tsx    SVG 3D spatial map
│       │   └── StateEmulator.tsx     Playable emulator
│       ├── hooks/
│       │   ├── useStory.ts           Pipeline fetch + pendingStoryId
│       │   └── useProgress.ts        SSE EventSource hook
│       └── types/index.ts
├── prometheus/prometheus.yml
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## API Reference

### `POST /api/generate`

```json
{
  "premise": "A forensic accountant discovers her murdered client was laundering money for three crime families",
  "genre": "thriller",
  "tone": 0.5
}
```

Response includes `token_spend`, `token_ceiling`, `agent_spans[]`, `validation`, `approved`, `error`.

### `GET /api/progress/{story_id}`

Server-Sent Events stream. Connect after POST /generate starts.

```
event: progress
data: {"stage": "structural-repair", "message": "Fixing 3 structural issue(s)…", "retry": 1}

event: done
data: {}
```

### `POST /api/validate`
Run sandbox validator only — no LLM, no Guardian.

### `POST /api/blueprint`
Generate 3D spatial transform from a story JSON.

### `GET /api/stories/{story_id}`
Retrieve a persisted story by ID (survives restarts).

---

## Tech Stack

| Layer | Technology |
|---|---|
| **AI Engineering Assistant** | **IBM Bob** — architecture, repair modes, Guardian integration, all debugging |
| **Content Safety** | **IBM Granite Guardian 3-8b** via watsonx.ai (harm/violence/hate/sexual/profanity) |
| **LLM Primary** | Groq `llama-3.3-70b-versatile` with exponential backoff retry |
| **LLM Fallback 1** | Groq `llama-3.1-8b-instant` (separate daily quota) |
| **LLM Fallback 2** | Google `gemini-2.5-flash` (different provider entirely) |
| **Orchestration** | LangGraph StateGraph |
| **Diff-patch repair** | `core/utils.merge_patch()` + 4 targeted repair prompts |
| **Schema sanitiser** | `_sanitise_schema()` — zero-token field repair at parse time |
| **Dangling ref fixer** | `_fix_dangling_refs()` — zero-token routing repair at parse time |
| **Token budget gates** | Pre-flight · Router gate · Generator guard (3 independent layers) |
| **Vector search** | FAISS + sentence-transformers `all-MiniLM-L6-v2` (genre-scoped) |
| **Progress streaming** | Server-Sent Events (`core/progress.py` bounded queue) |
| **Story persistence** | Atomic JSON file store (`data/stories/`) |
| **Backend** | FastAPI + Uvicorn (Python 3.11) |
| **Graph analysis** | NetworkX (cycle detection + invalid_edges extraction) |
| **Frontend** | React 18 + TypeScript + Vite |
| **Story graph** | React Flow (BFS-layout, tone-coloured nodes) |
| **Charts** | Recharts |
| **Metrics** | Prometheus + Grafana 11.4.0 |
| **Infrastructure** | Docker Compose (4 services: api · frontend · prometheus · grafana) |

---

## Security

- All containers run as non-root users
- nginx pinned to `nginx:alpine3.21`, Grafana pinned to `11.4.0`
- API keys injected via `.env` (never committed — gitignored)
- Generated stories saved to `data/stories/` (gitignored)
- CORS restricted to frontend origin
- IBM Granite Guardian scans every story for harmful content before approval

---

## Verified Results

Both test premises ran successfully end-to-end:

| Story | Scenes | Tokens | Guardian | Result |
|---|---|---|---|---|
| **Deadly Ledger** (forensic accountant) | 25 | 2,932 (7%) | ✓ 0 violations | ✅ APPROVED |
| **Rogue Mercenary** (mercenary + child target) | 31 | 3,513 (9%) | ✓ 0 violations | ✅ APPROVED |

Pipeline trace (Rogue Mercenary):
```
Story Generator       8,327ms    3,513 tokens    ✓
Style Vault           2,550ms    —               ✓   0 violations
Sandbox Validator        26ms    —               ✓   0 cycles · 0 errors
IBM Granite Guardian 115,157ms   —               ✓   0 violations
Compliance               72ms    —               ✓   fp: 48911ad6afc0f57d…
```

> Guardian takes ~115s on the Lite/free plan — 31 scenes × 5 categories = 155 watsonx.ai API calls through the shared inference endpoint.
