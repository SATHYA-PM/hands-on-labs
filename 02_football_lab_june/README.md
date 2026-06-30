# VanguardPitch.AI ⚽🤖

> **An Enterprise-Grade Sports Analytics & Ingestion Pipeline for the 2026 World Cup**
> Powered by IBM Granite-4, LangChain, IBM Docling, & Scikit-Learn. Governed via Context Forge Telemetry.

---

## 📌 Executive Overview

VanguardPitch.AI is a production-grade sports analytics decision-support dashboard engineered to eliminate human emotional bias, media punditry, and subjective guesswork from football forecasting.

By fusing traditional deterministic machine learning with modern generative cognitive reasoning and strict operational LLMOps governance, the platform delivers mathematically objective and psychologically grounded match intelligence briefs tailored specifically for high-stakes elimination tournaments.

---

## 🏗️ System Architecture & Ingestion Framework

The system decouples data ingestion, statistical probability modeling, and cognitive analysis into a distinct pipeline architecture:

```
User Interface / Streamlit Front-End
        │                          │
        ▼                          ▼
Cached Scikit-Learn ML       IBM Docling Parser
Model (match_predictor.pkl)  Engine (PDF → Markdown)
        │                          │
        ▼                          ▼
Crunch-Time Stress          Truncated Markdown
Algorithm                   Context (800 chars)
        │                          │
        ▼                          ▼
Exact Match Win         ──► LangChain Core Layer
Vectors %                    │
Crunch-Time Stress      Dynamic Prompt Template Engine
Vectors %                    │
                        IBM Granite-4 Reasoning Engine
                        (ibm/granite-4-h-small via Watsonx)
                             │
                        Regex Output Extraction Parser
                             │
                        Clean Sequenced 1. 2. 3.
                        Psychological Brief
                             │
                        Observability Payload
                             │
                        Context Forge Proxy Gateway
                        (Governance Layer — port 4444)
```

1. **Deterministic Baseline ML Engine:** A predictive classifier (`match_predictor.pkl`) trained on historical data spanning international match results since 1872. It ingests team match inputs to calculate foundational win/draw probability vectors.
2. **Unstructured Cognitive Document Ingestion:** Uses **IBM Docling** to parse unstructured tactical scouting report PDFs under rigid performance bounds, stripping metadata and converting raw documents into clean semantic text chunks (truncated to 800 chars to stay within model token budget).
3. **Advanced LLM Orchestration:** An optimized **LangChain LCEL (LangChain Expression Language)** pipeline routes the computed probability metrics and parsed scouting context into the **ibm/granite-4-h-small** foundation model via IBM Watsonx.
4. **Deterministic Output Controls:** Custom regex parsers and strict response filter arrays intercept the LLM output to clean out instructions or system bleeds, outputting a precise, sequentially structured 3-sentence psychological tactical brief.
5. **Observability & Operational Auditing:** Every predictive pipeline execution triggers a secure runtime telemetry logging event. The app authenticates via local `.env` encrypted secrets using JWT protocols to stream transaction JSON payloads directly into an isolated **IBM Context Forge proxy gateway** running locally inside Docker containers on port `4444`.

---

## 🛠️ Core Tech Stack

| Layer | Technology |
|---|---|
| **UI / Frontend** | Streamlit `1.58.0` |
| **LLM Orchestration** | LangChain LCEL (`langchain-core 1.4.8`, `langchain-ibm 1.1.0`) |
| **Foundation Model** | IBM Granite-4 (`ibm/granite-4-h-small`) via IBM Watsonx |
| **Document Parsing** | IBM Docling `2.107.0` (PDF → Markdown extraction) |
| **Statistical Modeling** | Scikit-Learn Classifier Pipeline + Joblib `1.5.3` |
| **Data Processing** | Pandas `3.0.3` |
| **Observability / Governance** | Docker + Context Forge MCP Gateway (port `4444`) |
| **Environment Management** | `python-dotenv 1.2.2` |
| **HTTP Client** | `requests 2.34.2` |

---

## 📁 Project Structure

```
02_football_lab_june/
├── 00_intro/
│   └── README (1).md                    # Lab introduction & overview
├── 01_get-started_with_bob/
│   └── get-started-with-ibm-bob (1).md  # IBM Bob setup guide
├── 02_main_lab_instructions/
│   └── ai-in-sports-football-predictions.md  # Full lab instructions
├── 03_jupyter_notebook/
│   ├── app.py                           # Streamlit application (main entry point)
│   ├── corelab_updated.ipynb            # Jupyter notebook (ML training pipeline)
│   ├── requirements.txt                 # Pinned Python dependencies
│   ├── scouting_report_brazil_argentina.pdf  # Sample scouting report for Docling
│   ├── data/
│   │   └── results.csv                  # Historical match dataset (1872–2026)
│   └── models/
│       ├── match_predictor.pkl          # Trained Scikit-Learn classifier
│       └── team_data.pkl                # Team stats + feature columns
├── 04_data/
│   └── results.csv                      # Source dataset
├── 05_images/
│   ├── dual-track architecture.png      # System architecture diagram
│   ├── VanguardAI.png                   # App logo
│   ├── Capture1–6.PNG                   # Lab screenshots
│   └── ...
├── clean_lab.env                        # Context Forge gateway config (safe defaults)
└── README.md                            # This file
```

---

## 🚀 Installation & Local Environment Setup

### 1. Clone the Repository

```bash
git clone https://github.com/IBM-SkillsBuild-AI-Builders-Challenge/hands-on-labs.git
cd hands-on-labs/02_football_lab_june
```

### 2. Install Python Dependencies

```bash
cd 03_jupyter_notebook
pip install -r requirements.txt
```

**Pinned versions:**

```
streamlit==1.58.0
pandas==3.0.3
joblib==1.5.3
python-dotenv==1.2.2
requests==2.34.2
langchain-ibm==1.1.0
langchain-core==1.4.8
docling==2.107.0
```

### 3. Configure Environment Secrets

Create a `.env` file inside `03_jupyter_notebook/` with your IBM Watsonx credentials:

```env
IBM_WATSONX_APIKEY=your_ibm_watsonx_api_key
IBM_PROJECT_ID=your_ibm_project_id
```

> ⚠️ **Never commit your `.env` file.** It is protected by `.gitignore`.

### 4. Start the Context Forge Gateway (Optional — for Telemetry)

The Context Forge MCP gateway runs in Docker on port `4444`. Apply the provided environment config:

```bash
# From 02_football_lab_june/
docker run -d -p 4444:4444 --env-file clean_lab.env context-forge-gateway
```

`clean_lab.env` contains safe non-secret gateway defaults:

```env
UAID_ALLOWED_DOMAINS=["*"]
SSRF_ALLOW_LOCALHOST=true
SSRF_ALLOW_PRIVATE_NETWORKS=true
```

### 5. Launch the Streamlit Application

```bash
cd 03_jupyter_notebook
streamlit run app.py
```

Open your browser at `http://localhost:8501`

---

## 📊 Live Simulation Deep-Dive: Brazil vs. Argentina

When executing a mock high-tension fixture under active match conditions, the application outputs perfectly synced operational logic loops:

**ML Classifier Evaluation:**
- Brazil Win Vector: **39.2%** | Draw Vector: **20.9%** | Argentina Win Vector: **39.9%**

**Dynamic Stress Modifiers:**
When unchecking *"Neutral Venue"* to simulate a home-crowd pressure constraint, the platform dynamically applies a **+15% away-game penalty matrix**, automatically scaling Brazil's internal Crunch-Time Pressure Index from **49.9%** up to **64.9%** while adjusting win vectors live.

**IBM Granite-4 Synthesized Psychological Brief:**

> **1.** The win probability of 39.2% for Brazil and 39.9% for Argentina creates a psychological battle before the match even begins, as both teams must reconcile nearly equal chances of victory with their own self-belief, potentially heightening pre-match anxiety and focus.
>
> **2.** Brazil's pressure index of 49.9% indicates a significant level of stress, combined with their recent form of 0.30 suggesting a dip in confidence, which could lead to lapses in composure in the final 15 minutes as they struggle to maintain poise under pressure.
>
> **3.** Argentina's pressure index of 35.0% suggests relatively stronger mental resilience, paired with a robust recent form of 0.60, allowing them to make calmer, more strategic decisions under stress, potentially giving them an edge in clutch moments.

---

## 🔒 Enterprise Security & Telemetry State Loop

For strict enterprise security isolation, client actions clear telemetry memory maps dynamically via `on_change` state callbacks whenever team selections change. The background JSON audit logger maps telemetry loops directly within the sidebar inspection portal:

```json
{
  "app": "VanguardPitch.AI",
  "match": "Brazil vs Argentina",
  "model": "ibm/granite-4-h-small",
  "prompt": "Brazil vs Argentina",
  "response": "1. With a nearly identical win probability of 39.2% for Brazil and 39.9% for Argentina..."
}
```

**Security design principles applied:**
- All secrets loaded exclusively from `.env` via `python-dotenv` — never hardcoded
- JWT token obtained per-session from Context Forge gateway (`/auth/login`) and cached for 4.5 minutes
- Gateway audit trail streamed via `Authorization: Bearer <token>` header
- Telemetry state cleared on every team change via `st.session_state` callbacks
- `.env` protected by `.gitignore` — credentials never committed to version control

---

## 🧠 Crunch-Time Pressure Index Formula

The pressure index is computed deterministically per team using:

```
base_pressure     = 35% (major tournament) or 10% (friendly)
form_deficit      = max(0, win_rate - recent_form)
pressure          = min(98%, base + (form_deficit × 45) + venue_penalty)
venue_penalty     = +15% for the away team when neutral venue is unchecked
```

This models psychological stress as a function of historical performance deficit and match-context stakes.

---

## 📓 Jupyter Notebook Pipeline (`corelab_updated.ipynb`)

The notebook contains the full end-to-end ML training pipeline:

1. **Data Ingestion** — loads `data/results.csv` (49,016 international matches, 1872–2026)
2. **Feature Engineering** — computes `winrate`, `goal_avg`, `recent_form`, `matches_played` per team
3. **Model Training** — trains a Scikit-Learn classifier on match outcome labels (`team_a_win`, `draw`, `team_b_win`)
4. **Model Serialization** — exports `models/match_predictor.pkl` and `models/team_data.pkl` via Joblib
5. **Validation** — evaluates accuracy and probability calibration on held-out test data

---

## 📚 Dataset

**Source:** [Kaggle — International football results from 1872 to 2026](https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017)

| Column | Description |
|---|---|
| `date` | Date of the match |
| `home_team` | Home team name |
| `away_team` | Away team name |
| `home_score` | Full-time home score (incl. extra time, excl. penalties) |
| `away_score` | Full-time away score (incl. extra time, excl. penalties) |
| `tournament` | Tournament name |
| `city` | City where the match was played |
| `country` | Country where the match was played |
| `neutral` | `TRUE`/`FALSE` — whether match was at a neutral venue |

---

## 🤝 Built With IBM Bob

This application was prototyped and engineered using **IBM Bob Code Assistant** — an AI-powered development tool that generated, debugged, and refined the entire codebase through natural language prompts.

> *"From 'I don't code' to 'I built an AI app!' — Bob makes it happen."*

---

## 🔗 Additional Resources

- [IBM Bob Documentation](https://bob.ibm.com/docs)
- [IBM Watsonx Platform](https://www.ibm.com/watsonx)
- [LangChain LCEL Docs](https://python.langchain.com/docs/expression_language/)
- [IBM Docling](https://github.com/DS4SD/docling)
- [Context Forge MCP Gateway](https://github.com/IBM/context-forge)
- [Kaggle Dataset](https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017)
