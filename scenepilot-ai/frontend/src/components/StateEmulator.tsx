import { useState, useEffect, useCallback } from "react";
import type { Scene } from "../types";
import { MIN_SCENES } from "../types";

interface PlayerState {
  currentSceneId: string;
  health: number;
  inventory: string[];
  visitedScenes: string[];
  log: string[];
  turnsPlayed: number;
}

function deriveHealthDelta(text: string): number {
  const lower = text.toLowerCase();
  if (/collapse|explosion|toxic|wound|critical|fatal|crush|bleed/.test(lower)) return -20;
  if (/damage|hurt|fall|shock|threat|danger|attack/.test(lower)) return -10;
  if (/safe|rest|heal|refuge|calm|shelter|medic/.test(lower)) return +10;
  if (/discover|key|tool|weapon|supply|find|grab/.test(lower)) return 0;
  return 0;
}

function deriveItem(text: string): string | null {
  const matches = text.match(
    /\b(keycard|key|badge|weapon|medkit|torch|map|device|crystal|potion|sword|shield|code|rope|signal)\b/i
  );
  return matches ? matches[1].toLowerCase() : null;
}

interface Props {
  scenes: Scene[];
  storyTitle: string | null;
}

export default function StateEmulator({ scenes, storyTitle }: Props) {
  const sceneMap = Object.fromEntries(scenes.map((s) => [s.id, s]));
  const root = scenes[0]?.id ?? "";

  const initialState = useCallback((): PlayerState => ({
    currentSceneId: root,
    health: 100,
    inventory: [],
    visitedScenes: [root],
    log: [`[Start] Entered ${root}`],
    turnsPlayed: 0,
  }), [root]);

  const [state, setState] = useState<PlayerState>(initialState);
  const currentScene = sceneMap[state.currentSceneId];

  // Reset when story changes
  useEffect(() => { setState(initialState()); }, [root, initialState]);

  function makeChoice(targetId: string, choiceLabel: string) {
    const targetScene = sceneMap[targetId];
    if (!targetScene) return;

    const delta = deriveHealthDelta(targetScene.text);
    const item  = deriveItem(targetScene.text);
    const newHealth = Math.max(0, Math.min(100, state.health + delta));
    const newInventory = item && !state.inventory.includes(item)
      ? [...state.inventory, item]
      : state.inventory;

    const logEntries = [
      `[Turn ${state.turnsPlayed + 1}] → "${choiceLabel}"`,
      `[Scene] ${targetId}`,
      ...(delta !== 0 ? [`[Vitality] ${delta > 0 ? "+" : ""}${delta}% → ${newHealth}%`] : []),
      ...(item && !state.inventory.includes(item) ? [`[Inventory] Acquired: ${item}`] : []),
    ];

    setState({
      currentSceneId:  targetId,
      health:          newHealth,
      inventory:       newInventory,
      visitedScenes:   [...state.visitedScenes, targetId],
      log:             [...state.log, ...logEntries],
      turnsPlayed:     state.turnsPlayed + 1,
    });
  }

  const isEnding     = !currentScene || currentScene.choices.length === 0;
  const isDead       = state.health <= 0;
  const healthColor  = state.health > 60 ? "#16a34a" : state.health > 30 ? "#d97706" : "#dc2626";
  const threatLevel  = state.health > 60 ? "STABLE" : state.health > 30 ? "ELEVATED" : "CRITICAL";
  const threatColor  = state.health > 60 ? "#16a34a" : state.health > 30 ? "#d97706" : "#dc2626";

  const isPartialStory = scenes.length < MIN_SCENES;

  return (
    <div className="emulator">
      {/* ── Partial-story warning ── */}
      {isPartialStory && (
        <div className="emulator-partial-warning">
          ⚠ Partial story ({scenes.length} of {MIN_SCENES}+ scenes) — the token budget
          was exhausted during generation. Some branches may be missing or lead to dead ends.
          Raise <code>TOKEN_BUDGET_LIMIT</code> in <code>.env</code> and regenerate for a
          complete narrative.
        </div>
      )}

      {/* ── Header ── */}
      <div className="emulator-header">
        <span className="emulator-title">🎮 Game State Emulator</span>
        <span className="emulator-story">{storyTitle ?? "Untitled"}</span>
        <button className="btn btn--ghost emulator-reset" onClick={() => setState(initialState())}>
          ↺ Reset
        </button>
      </div>

      <div className="emulator-body">

        {/* ── Left: Player stats ── */}
        <div className="emulator-stats">
          <div className="stat-block">
            <div className="stat-label">Current Node</div>
            <div className="stat-value mono">{state.currentSceneId}</div>
          </div>
          <div className="stat-block">
            <div className="stat-label">❤ Vitality</div>
            <div className="stat-value" style={{ color: healthColor }}>{state.health}%</div>
            <div className="stat-bar-track">
              <div className="stat-bar-fill" style={{ width: `${state.health}%`, background: healthColor }} />
            </div>
          </div>
          <div className="stat-block">
            <div className="stat-label">⚠ Threat Level</div>
            <div className="stat-value" style={{ color: threatColor, fontSize: "0.8rem" }}>{threatLevel}</div>
          </div>
          <div className="stat-block">
            <div className="stat-label">🎒 Inventory</div>
            {state.inventory.length === 0
              ? <div className="stat-empty">Empty</div>
              : <div className="inventory-list">
                  {state.inventory.map((item, i) => (
                    <span key={i} className="inventory-chip">{item}</span>
                  ))}
                </div>
            }
          </div>
          <div className="stat-block">
            <div className="stat-label">Turns Played</div>
            <div className="stat-value">{state.turnsPlayed}</div>
          </div>
          <div className="stat-block">
            <div className="stat-label">Scenes Visited</div>
            <div className="stat-value">{state.visitedScenes.length} / {scenes.length}</div>
          </div>
        </div>

        {/* ── Centre: Active scene ── */}
        <div className="emulator-scene">
          {isDead ? (
            <div className="emulator-gameover">
              <div className="gameover-icon">☠</div>
              <h3>Game Over</h3>
              <p>Vitality reached 0. The story ends here.</p>
              <button className="btn btn--primary" onClick={() => setState(initialState())}>↺ Try Again</button>
            </div>
          ) : isEnding ? (
            <div className="emulator-ending">
              <div className="ending-icon">★</div>
              <h3>Story Complete</h3>
              <p className="emulator-text">{currentScene?.text}</p>
              <p className="ending-meta">
                Completed in {state.turnsPlayed} turns · {state.visitedScenes.length} scenes visited
              </p>
              <button className="btn btn--secondary" onClick={() => setState(initialState())}>↺ Play Again</button>
            </div>
          ) : (
            <>
              <div className="emulator-scene-id">{state.currentSceneId}</div>
              <p className="emulator-text">{currentScene?.text}</p>
              <div className="emulator-choices">
                <div className="choices-label">Choose your action:</div>
                {currentScene?.choices.map((choice, i) => (
                  <button
                    key={i}
                    className="choice-btn"
                    onClick={() => choice.next && makeChoice(choice.next, choice.text)}
                    disabled={!choice.next}
                  >
                    <span className="choice-arrow">→</span>
                    {choice.text}
                    {!choice.next && <span className="choice-tag">ending</span>}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* ── Right: Session log ── */}
        <div className="emulator-log">
          <div className="log-header">Session Log</div>
          <div className="log-entries">
            {[...state.log].reverse().map((entry, i) => (
              <div key={i} className={`log-entry ${entry.startsWith("[Vitality]") ? (entry.includes("-") ? "log-warn" : "log-good") : entry.startsWith("[Inventory]") ? "log-item" : ""}`}>
                {entry}
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
