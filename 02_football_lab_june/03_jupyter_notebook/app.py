import os
import tempfile
import requests
import streamlit as st
import pandas as pd
import joblib
from pathlib import Path
from dotenv import load_dotenv

# --- LangChain + IBM Granite-4 ---
from langchain_ibm import WatsonxLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# --- Docling ---
from docling.document_converter import DocumentConverter

# --- Context Forge Gateway ---
CONTEXT_FORGE_URL  = os.environ.get("MCPGATEWAY_URL", "http://localhost:4444")
CONTEXT_FORGE_CREDS = {
    "username": os.environ.get("CONTEXT_FORGE_ADMIN_EMAIL", "admin@example.com"),
    "password": os.environ.get("CONTEXT_FORGE_ADMIN_PASSWORD", "changeme"),
}

@st.cache_data(ttl=270, show_spinner=False)
def get_gateway_token() -> str:
    """Obtains a JWT from the Context Forge gateway (cached 4.5 min)."""
    try:
        r = requests.post(
            f"{CONTEXT_FORGE_URL}/auth/login",
            json=CONTEXT_FORGE_CREDS,
            timeout=3,
        )
        if r.status_code == 200:
            data = r.json()
            return next(iter(data.values()), "")
    except Exception:
        pass
    return ""

def log_to_context_forge(team_a: str, team_b: str, prompt: str, response: str):
    """Stores the last LLM call payload in session state for sidebar display."""
    payload = {
        "app":      "VanguardPitch.AI",
        "match":    f"{team_a} vs {team_b}",
        "model":    "ibm/granite-4-h-small",
        "prompt":   prompt[:300],
        "response": response[:300],
    }
    try:
        st.session_state["gateway_logs"] = [payload]
    except Exception:
        pass

# --- LOAD LOCAL ENVIRONMENT SECRETS ---
load_dotenv()

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Soccer 2026 Match Predictor [AI-Powered by IBM Granite]",
    page_icon="⚽",
    layout="centered",
)

# --- WORKSPACE LOADERS ---
@st.cache_resource
def load_artifacts():
    ml_model  = joblib.load(Path("models/match_predictor.pkl"))
    team_data = joblib.load(Path("models/team_data.pkl"))
    return ml_model, team_data["team_stats"], team_data["feature_cols"]

ml_model, team_stats, feature_cols = load_artifacts()

# --- DOCLING: PDF SCOUTING REPORT PARSER ---
def extract_scouting_context(uploaded_file) -> str:
    """Uses Docling to extract text from an uploaded PDF.
    Falls back to pypdf plain-text extraction if Docling runs out of memory."""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name

        # Try Docling page by page — stop as soon as we get text
        converter = DocumentConverter()
        for end_page in [5, 3, 1]:
            try:
                result = converter.convert(tmp_path, page_range=(1, end_page), raises_on_error=False)
                text = result.document.export_to_markdown() or ""
                if text.strip():
                    return text[:800].strip()
            except Exception:
                continue

        # Fallback: use pypdf (pure Python, no C++ memory issues)
        try:
            import pypdf
            reader = pypdf.PdfReader(tmp_path)
            text = ""
            for page in reader.pages[:10]:
                text += page.extract_text() or ""
                if len(text) >= 800:
                    break
            if text.strip():
                return text[:800].strip()
        except Exception:
            pass

        return "[Could not extract text from this PDF — try a smaller or text-based PDF]"

    except Exception as e:
        return f"[Docling parse error: {str(e)}]"

# --- LANGCHAIN: WATSONX LLM + PROMPT TEMPLATE + CHAIN (LCEL) ---
@st.cache_resource
def build_langchain():
    """Builds and caches the LangChain LCEL chain: prompt | WatsonxLLM | parser."""
    llm = WatsonxLLM(
        model_id="ibm/granite-4-h-small",
        url="https://us-south.ml.cloud.ibm.com",
        apikey=os.environ.get("IBM_WATSONX_APIKEY"),
        project_id=os.environ.get("IBM_PROJECT_ID"),
        params={
            "decoding_method": "greedy",
            "max_new_tokens":  450,
            "min_new_tokens":  1,
        },
    )

    # Keep your PromptTemplate and LCEL pipeline exactly as they were
    prompt = PromptTemplate(
        input_variables=[
            "team_a", "team_b",
            "p_a", "p_b", "p_draw",
            "form_a", "form_b",
            "pressure_a", "pressure_b",
            "is_major_tournament", "is_neutral",
            "scouting_context",
        ],
        template=(
            "You are a sports psychologist analyzing a 2026 World Cup match.\n\n"
            "Match: {team_a} vs {team_b}\n"
            "Data:\n"
            "- {team_a}: win probability {p_a}%, recent form {form_a}, pressure index {pressure_a}%\n"
            "- {team_b}: win probability {p_b}%, recent form {form_b}, pressure index {pressure_b}%\n"
            "- Draw probability: {p_draw}%\n"
            "- Major tournament: {is_major_tournament}, Neutral venue: {is_neutral}\n"
            "{scouting_context}\n"
            "Write 3 numbered sentences of psychological analysis:\n"
            "1."
        ),
    )
    # LCEL pipeline: prompt → llm → string parser
    return prompt | llm | StrOutputParser()
    
def call_langchain(chain, **kwargs):
    """Invokes the LCEL chain and returns the AI analysis text."""
    try:
        return chain.invoke(kwargs).strip()
    except Exception as e:
        return (
            f"ℹ️ [LangChain Error] Chain invocation failed. "
            f"Check your .env credentials. Details: {str(e)}"
        )

# --- SIDEBAR: CONTEXT FORGE STATUS + DOCLING PDF UPLOADER ---
gateway_online = False
with st.sidebar:
    st.header("🌐 Context Forge Gateway")
    try:
        r = requests.get(f"{CONTEXT_FORGE_URL}/health", timeout=3)
        if r.status_code == 200:
            st.success("Gateway: Online ✅")
            gateway_online = True
        else:
            st.warning(f"Gateway: Unexpected status {r.status_code}")
    except Exception as e:
        st.error(f"Gateway: Offline ❌ ({e})")

    if gateway_online:
        with st.expander("🔍 Inspect Option 3 Gateway Logs"):
            local_logs = st.session_state.get("gateway_logs", [])
            if local_logs:
                st.caption("📦 Last pipeline call:")
                st.json(local_logs[-1])
            else:
                st.caption("Run a prediction to see telemetry here.")
            # --- Gateway audit trail ---
            try:
                token = get_gateway_token()
                if token:
                    trail = requests.get(
                        f"{CONTEXT_FORGE_URL}/api/logs/audit-trails",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=3,
                    )
                    if trail.status_code == 200:
                        entries = trail.json()
                        if isinstance(entries, list) and entries:
                            st.caption("📋 Gateway audit trail (latest):")
                            st.json(entries[-1])
            except Exception:
                pass

    st.divider()
    st.header("📄 Scouting Report (Optional)")
    st.caption("Upload a PDF match report. Docling extracts the text and enriches the AI analysis.")
    uploaded_pdf = st.file_uploader("Upload PDF", type=["pdf"], label_visibility="collapsed")
    scouting_text = ""
    if uploaded_pdf:
        with st.spinner("Docling is parsing your scouting report..."):
            scouting_text = extract_scouting_context(uploaded_pdf)
        if scouting_text.startswith("[Docling"):
            st.error(scouting_text)
            scouting_text = ""
        else:
            st.success(f"Parsed {len(scouting_text)} characters from report.")
            with st.expander("Preview extracted text"):
                st.text(scouting_text[:400] + ("..." if len(scouting_text) > 400 else ""))

# --- USER INTERFACE ---
st.title("⚽ Soccer 2026 Match Predictor")
st.caption("AI-Powered by IBM Granite-4 via LangChain + Docling | Prototyped using IBM Bob Code Assistant")

team_names = sorted(team_stats.keys())

def _clear_telemetry():
    """Called by on_change on either selectbox — clears stale telemetry before next render."""
    st.session_state.pop("gateway_logs", None)

col1, col2 = st.columns(2)
with col1:
    default_a = team_names.index("Brazil") if "Brazil" in team_names else 0
    team_a = st.selectbox("Team A", team_names, index=default_a, key="sel_team_a", on_change=_clear_telemetry)
with col2:
    default_b = team_names.index("Argentina") if "Argentina" in team_names else 1
    team_b = st.selectbox("Team B", team_names, index=default_b, key="sel_team_b", on_change=_clear_telemetry)

is_neutral          = st.checkbox("Neutral venue", value=True)
is_major_tournament = st.checkbox("Major tournament (e.g. World Cup)", value=True)

if st.button("Predict Match & Analyze Pressure", type="primary", use_container_width=True):
    if team_a == team_b:
        st.error("Please pick two different global squads.")
    else:
        # Build feature row
        row = pd.DataFrame([{
            "team_a_winrate":      team_stats[team_a]["winrate"],
            "team_b_winrate":      team_stats[team_b]["winrate"],
            "team_a_goal_avg":     team_stats[team_a]["goal_avg"],
            "team_b_goal_avg":     team_stats[team_b]["goal_avg"],
            "team_a_recent_form":  team_stats[team_a]["recent_form"],
            "team_b_recent_form":  team_stats[team_b]["recent_form"],
            "is_neutral":          int(is_neutral),
            "is_major_tournament": int(is_major_tournament),
        }]).reindex(columns=feature_cols)

        # ML probabilities
        proba  = ml_model.predict_proba(row)[0]
        p_a    = float(proba[0])
        p_draw = float(proba[1])
        p_b    = float(proba[2])

        # Probability metrics
        m1, m2, m3 = st.columns(3)
        m1.metric(f"{team_a} wins", f"{p_a * 100:.1f}%")
        m2.metric("Draw",           f"{p_draw * 100:.1f}%")
        m3.metric(f"{team_b} wins", f"{p_b * 100:.1f}%")

        st.progress(p_a,    text=f"{team_a} Match Win Vector — {p_a * 100:.1f}%")
        st.progress(p_draw, text=f"Match Draw Vector — {p_draw * 100:.1f}%")
        st.progress(p_b,    text=f"{team_b} Match Win Vector — {p_b * 100:.1f}%")

        # Team stats table
        st.table(pd.DataFrame({
            "Win Rate":         [team_stats[team_a]["winrate"],        team_stats[team_b]["winrate"]],
            "Avg Goals Scored": [team_stats[team_a]["goal_avg"],       team_stats[team_b]["goal_avg"]],
            "Recent Form (10)": [team_stats[team_a]["recent_form"],    team_stats[team_b]["recent_form"]],
            "Matches Played":   [team_stats[team_a]["matches_played"], team_stats[team_b]["matches_played"]],
        }, index=[team_a, team_b]))

        # --- CRUNCH-TIME PRESSURE INDEX ---
        st.divider()
        st.subheader("🧠 Crunch-Time Pressure Index Analyzer")
        st.caption("Human performance metrics evaluating team stress levels under match conditions.")

        base_press_a   = 35 if is_major_tournament else 10
        base_press_b   = 35 if is_major_tournament else 10
        form_deficit_a = max(0, team_stats[team_a]["winrate"] - team_stats[team_a]["recent_form"])
        form_deficit_b = max(0, team_stats[team_b]["winrate"] - team_stats[team_b]["recent_form"])
        pressure_a     = min(98.0, base_press_a + (form_deficit_a * 45) + (0 if is_neutral else 15))
        pressure_b     = min(98.0, base_press_b + (form_deficit_b * 45) + (15 if not is_neutral else 0))

        pc1, pc2 = st.columns(2)
        with pc1:
            st.metric(f"{team_a} Stress Vector", f"{pressure_a:.1f}%")
            st.progress(pressure_a / 100.0)
        with pc2:
            st.metric(f"{team_b} Stress Vector", f"{pressure_b:.1f}%")
            st.progress(pressure_b / 100.0)

        # Build scouting context block for the prompt
        scouting_block = (
            f"Scouting Report Context (from uploaded PDF):\n{scouting_text}\n\n"
            if scouting_text else ""
        )

        # --- LANGCHAIN + DOCLING AI ANALYSIS ---
        chain = build_langchain()
        label = "🤖 **IBM Granite-4 via LangChain"
        label += " + Docling Scouting Context" if scouting_text else ""
        label += " — Human Performance Analysis:**"
        st.info(label)
        ai_analysis = call_langchain(
            chain,
            team_a=team_a,
            team_b=team_b,
            p_a=f"{p_a*100:.1f}",
            p_b=f"{p_b*100:.1f}",
            p_draw=f"{p_draw*100:.1f}",
            form_a=f"{team_stats[team_a]['recent_form']:.2f}",
            form_b=f"{team_stats[team_b]['recent_form']:.2f}",
            pressure_a=f"{pressure_a:.1f}",
            pressure_b=f"{pressure_b:.1f}",
            is_major_tournament=str(is_major_tournament),
            is_neutral=str(is_neutral),
            scouting_context=scouting_block,
        )
        # --- RESILIENT CLEANED OUTPUT DISPLAY ---
        if ai_analysis:
            import re
            
            # 1. Normalize formatting: split by numbers if the model didn't use newlines
            # This finds patterns like "2. " or "3. " and splits the text cleanly
            raw_segments = re.split(r'\s*(?=\b\d+\.\s)', ai_analysis)
            
            # 2. Clean out empty spaces and leaked system instructions
            # Patterns that indicate leaked system instructions rather than analysis
            _leak_patterns = (
                "use only info",
                "psychological pdf",
                "irrelevant for this analysis",
                "do not use",
                "do not repeat",
                "results and match details",
                "start directly with",
                "without a summary",
                "end the response with",
                "the end.",
                "involves '",
                "at least once",
                "overall, what can be said",
                "what can be said about",
            )
            filtered_lines = [
                seg.strip() for seg in raw_segments
                if seg.strip()
                and not seg.strip().lower().startswith("note:")
                and not any(p in seg.lower() for p in _leak_patterns)
            ]
            
            # 3. Standardize numbering and enforce clean line spacing
            clean_sentences = []
            for idx, line in enumerate(filtered_lines, start=1):
                content = re.sub(r'^\d+\.\s*', '', line).strip()  # Strip existing numbers
                if content:  # Skip empty segments
                    clean_sentences.append(f"{idx}. {content}")
            
            # Join with markdown double-newlines for a crisp visual list
            final_output = "\n\n".join(clean_sentences)
            st.write(final_output)
        else:
            st.write(ai_analysis)

        # --- LOG TO CONTEXT FORGE GATEWAY ---
        log_to_context_forge(
            team_a=team_a,
            team_b=team_b,
            prompt=scouting_block + f"{team_a} vs {team_b}",
            response=ai_analysis,
        )
