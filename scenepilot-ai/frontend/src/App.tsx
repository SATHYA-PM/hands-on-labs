import { useState } from "react";
import type { Scene, Genre } from "./types";
import { useStory } from "./hooks/useStory";
import PremiseInput from "./components/PremiseInput";
import StoryTree from "./components/StoryTree";
import SceneInspector from "./components/SceneInspector";
import ValidationReport from "./components/ValidationReport";
import CostDashboard from "./components/CostDashboard";
import DemoLibrary from "./components/DemoLibrary";
import BlueprintPanel from "./components/BlueprintPanel";
import StateEmulator from "./components/StateEmulator";
import "./App.css";

type Tab = "tree" | "validation" | "cost" | "export" | "blueprint" | "emulator";

// Static metadata for each demo sample — used to pre-fill the form fields.
const SAMPLE_PREFILL: Record<string, { premise: string; genre: Genre; tone: number }> = {
  heist_thriller: {
    premise: "You are a master thief hired to steal the Kohinoor replica from a heavily guarded museum — but your partner just went dark minutes before the heist begins.",
    genre: "thriller",
    tone: 0.2,
  },
  fantasy_rpg: {
    premise: "Ember, a young rune-smith's apprentice, must recover the Forgotten Crown before an ancient curse turns the kingdom to ash.",
    genre: "fantasy",
    tone: 0.65,
  },
  product_launch: {
    premise: "You have 24 hours to launch your SaaS product before a well-funded competitor beats you to market.",
    genre: "marketing",
    tone: 0.75,
  },
  space_escape: {
    premise: "The life support on Helix Station is failing and the escape pods are locked behind a corrupted AI you must reason with or override.",
    genre: "sci-fi",
    tone: 0.3,
  },
  edu_quiz_tree: {
    premise: "Join Pip the water droplet on an interactive adventure through evaporation, condensation, and precipitation.",
    genre: "educational",
    tone: 0.85,
  },
};

export default function App() {
  const { status, result, error, generate, loadSample, reset } = useStory();
  const [selectedScene,  setSelectedScene]  = useState<Scene | null>(null);
  const [activeTab,      setActiveTab]      = useState<Tab>("tree");
  const [premiseLen,     setPremiseLen]     = useState(0);
  const [selectedSample, setSelectedSample] = useState<string | null>(null);

  const isLoading = status === "generating" || status === "validating";

  // Called when the Generate Story button is clicked.
  // If a demo sample is locked in, run loadSample; otherwise run the live LLM pipeline.
  function handleGenerate(premise: string, genre: Genre, tone: number) {
    setSelectedScene(null);
    setActiveTab("tree");
    if (selectedSample) {
      loadSample(selectedSample);
    } else {
      generate(premise, genre, tone);
    }
  }

  // Called when a demo card is clicked — select only, do NOT execute.
  function handleSelectSample(name: string) {
    // Toggle off if already selected
    setSelectedSample((prev) => (prev === name ? null : name));
  }

  function handleExport(format: "json" | "markdown" | "twine") {
    if (!result?.scenes) return;
    const story = { title: result.title, scenes: result.scenes };
    if (format === "json") {
      download(new Blob([JSON.stringify(story, null, 2)], { type: "application/json" }), `${slug(result.title)}.json`);
    } else if (format === "markdown") {
      download(new Blob([toMarkdown(story)], { type: "text/markdown" }), `${slug(result.title)}.md`);
    } else {
      download(new Blob([toTwine(story)], { type: "text/plain" }), `${slug(result.title)}.tw`);
    }
  }

  const scenes = result?.scenes ?? [];

  return (
    <div className="app">

      {/* ── Header ── */}
      <header className="app-header">
        <div className="header-brand">
          <span className="brand-icon">◈</span>
          <span className="brand-name">ScenePilot AI</span>
          <span className="brand-tagline">AI narrative generator + quality gate</span>
        </div>
        {result && (
          <button className="btn btn--ghost" onClick={() => { reset(); setSelectedSample(null); }}>← New Story</button>
        )}
      </header>

      <div className="app-body">

        {/* ── Left sidebar ── */}
        <aside className="sidebar">
          <div className="sidebar-inner">
            <PremiseInput
              onGenerate={handleGenerate}
              isLoading={isLoading}
              onPremiseChange={setPremiseLen}
              externalValues={selectedSample ? SAMPLE_PREFILL[selectedSample] ?? null : null}
              onUserEdit={() => setSelectedSample(null)}
            />
            <DemoLibrary
              onSelect={handleSelectSample}
              selectedSample={selectedSample}
              isLoading={isLoading}
            />
          </div>
          {/* Bug fix: do NOT use form="premise-form" here — that caused demo card
              clicks to also submit the form. Use onClick to call the form's own
              submit handler instead. */}
          <div className="sidebar-footer">
            <button
              type="button"
              className="btn btn--primary generate-btn"
              disabled={isLoading || premiseLen < 10}
              onClick={() => document.getElementById("premise-form")?.dispatchEvent(
                  new Event("submit", { bubbles: true, cancelable: true })
                )}
              >
                {isLoading
                  ? "Generating…"
                  : selectedSample
                    ? `✦ Load "${selectedSample.replace(/_/g, " ")}"`
                    : "✦ Generate Story"}
            </button>
          </div>
        </aside>

        {/* ── Main ── */}
        <main className="main">

          {/* Status */}
          {isLoading && (
            <div className="status-bar status-bar--loading">
              <span className="spinner" />
              {status === "generating" ? "Generating branching narrative…" : "Running validation pipeline…"}
            </div>
          )}
          {error && (
            <div className="status-bar status-bar--error">✗ {error}</div>
          )}

          {result ? (
            <>
              {/* Story bar */}
              <div className="story-bar">
                <span className="story-bar-title">{result.title}</span>
                <span className={`approved-badge ${result.approved ? "approved-badge--pass" : "approved-badge--fail"}`}>
                  {result.approved ? "Approved" : "Rejected"}
                </span>
                <span className="story-bar-meta">{scenes.length} scenes</span>
              </div>

              {/* Tabs */}
              <nav className="tabs">
                <span className="tab-group-label">Narrative</span>
                {(["tree", "validation", "cost", "export"] as Tab[]).map((t) => (
                  <button key={t} className={`tab ${activeTab === t ? "tab--active" : ""}`} onClick={() => setActiveTab(t)}>
                    {t === "tree"       && "Story Tree"}
                    {t === "validation" && "Validation Report"}
                    {t === "cost"       && "Cost Dashboard"}
                    {t === "export"     && "Export"}
                  </button>
                ))}
                <span className="tab-group-divider" />
                <span className="tab-group-label tab-group-label--engine">Game Engine</span>
                <button className={`tab tab--engine ${activeTab === "blueprint" ? "tab--active" : ""}`} onClick={() => setActiveTab("blueprint")}>
                  ⬡ 3D Blueprint
                </button>
                <button className={`tab tab--engine ${activeTab === "emulator" ? "tab--active" : ""}`} onClick={() => setActiveTab("emulator")}>
                  🎮 Emulator
                </button>
              </nav>

              {/* Tab content */}
              <div className="tab-content">

                {activeTab === "tree" && scenes.length > 0 && (
                  <div className="tree-layout">
                    <div className="tree-canvas-wrap">
                      <StoryTree
                        scenes={scenes}
                        onSelectScene={setSelectedScene}
                        selectedId={selectedScene?.id}
                      />
                    </div>
                    <div className="inspector-panel">
                      <div className="inspector-panel-header">Scene Inspector</div>
                      <div className="inspector-body">
                        <SceneInspector scene={selectedScene} />
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === "validation" && (
                  <div className="tab-scroll">
                    <ValidationReport
                      validation={result.validation}
                      agentSpans={result.agent_spans}
                      tokenSpend={result.token_spend}
                      approved={result.approved}
                      error={result.error}
                    />
                  </div>
                )}

                {activeTab === "cost" && (
                  <div className="tab-scroll">
                    <CostDashboard spans={result.agent_spans} tokenSpend={result.token_spend} tokenCeiling={result.token_ceiling} />
                  </div>
                )}

                {activeTab === "export" && (
                  <div className="tab-scroll">
                    <div className="export-panel">
                      <h3>Export Story</h3>
                      <p>Download the generated story in your preferred format.</p>
                      <div className="export-buttons">
                        <button className="btn btn--primary"   onClick={() => handleExport("json")}>↓ Download JSON</button>
                        <button className="btn btn--secondary" onClick={() => handleExport("markdown")}>↓ Download Markdown</button>
                        <button className="btn btn--secondary" onClick={() => handleExport("twine")}>↓ Download Twine (.tw)</button>
                      </div>
                      <div className="export-formats">
                        <div className="export-format-row">
                          <span className="export-format-name">JSON</span>
                          <span className="export-format-desc">Raw story graph — scenes + choices, suitable for any engine or further processing.</span>
                        </div>
                        <div className="export-format-row">
                          <span className="export-format-name">Markdown</span>
                          <span className="export-format-desc">Human-readable document with tone annotations. Great for writers and reviewers.</span>
                        </div>
                        <div className="export-format-row">
                          <span className="export-format-name">Twine (.tw)</span>
                          <span className="export-format-desc">Twee 3 notation. Import directly into Twine 2 (File → Import) or compile with Tweego.</span>
                        </div>
                      </div>
                      <div className="export-preview">
                        <pre>{JSON.stringify({ title: result.title, scenes: scenes.slice(0, 2) }, null, 2)}…</pre>
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === "blueprint" && (
                  <div className="tab-content-fill">
                    <BlueprintPanel scenes={scenes} storyId={result.story_id} />
                  </div>
                )}

                {activeTab === "emulator" && (
                  <div className="tab-content-fill">
                    <StateEmulator scenes={scenes} storyTitle={result.title} />
                  </div>
                )}

              </div>
            </>
          ) : (
            !isLoading && (
              <div className="empty-state">
                <div className="empty-icon">◈</div>
                <h3>Enter a premise and click Generate</h3>
                <p>Or load a one-click demo sample from the left panel.</p>
              </div>
            )
          )}

        </main>
      </div>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function slug(title: string | null | undefined) {
  return (title ?? "story").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function toMarkdown(story: { title: string | null; scenes: Scene[] }): string {
  const lines: string[] = [`# ${story.title ?? "Story"}`, ""];
  for (const scene of story.scenes) {
    lines.push(`## ${scene.id}`, `> *Tone: ${scene.tone}*`, "", scene.text, "");
    if (scene.choices.length > 0) {
      lines.push("**Choices:**");
      for (const c of scene.choices) lines.push(`- ${c.text} → ${c.next ?? "[ ending ]"}`);
      lines.push("");
    } else {
      lines.push("*[ End of path ]*", "");
    }
  }
  return lines.join("\n");
}

function toTwine(story: { title: string | null; scenes: Scene[] }): string {
  // Generates Twee 3 notation (.tw) compatible with Twine 2 / Tweego.
  // Format: :: PassageName [tags]\npassage content\n\n
  const title = story.title ?? "Story";
  const lines: string[] = [
    `:: StoryTitle`,
    title,
    ``,
    `:: StoryData`,
    JSON.stringify({ ifid: crypto.randomUUID(), format: "Harlowe", "format-version": "3.3.9", zoom: 1 }),
    ``,
  ];
  for (const scene of story.scenes) {
    const tags = `[tone-${scene.tone}${scene.choices.length === 0 ? " ending" : ""}]`;
    lines.push(`:: ${scene.id} ${tags}`);
    lines.push(scene.text);
    lines.push("");
    for (const c of scene.choices) {
      const target = c.next ?? scene.id;
      lines.push(`[[${c.text}|${target}]]`);
    }
    lines.push("");
  }
  return lines.join("\n");
}
