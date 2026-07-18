import { useState, useEffect } from "react";
import type { Scene } from "../types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

interface SpatialNode {
  scene_id: string;
  room_name: string;
  tone: string;
  is_terminal: boolean;
  transform: {
    position: [number, number, number];
    rotation: [number, number, number];
    scale:    [number, number, number];
  };
  bounds: { width: number; height: number; depth: number };
  assets_to_load: string[];
  triggers: Array<{
    choice_index: number;
    choice_label: string;
    target_scene: string;
    interaction_type: string;
    distance_metres: number;
  }>;
}

interface Blueprint {
  story_id: string;
  engine_formats: string[];
  world_bounds: { x_extent: number; z_extent: number; y_extent: number };
  stats: { total_rooms: number; terminal_rooms: number; max_depth: number; total_triggers: number };
  spatial_nodes: SpatialNode[];
}

const TONE_COLORS: Record<string, string> = {
  tense: "#f59e0b", hopeful: "#22c55e", dark: "#6b7280", neutral: "#3b82f6", playful: "#a855f7",
};

interface Props {
  scenes: Scene[];
  storyId: string;
}

export default function BlueprintPanel({ scenes, storyId }: Props) {
  const [blueprint, setBlueprint] = useState<Blueprint | null>(null);
  const [loading,   setLoading]   = useState(false);
  const [selected,  setSelected]  = useState<SpatialNode | null>(null);
  const [view,      setView]      = useState<"map" | "json">("map");

  useEffect(() => {
    if (!scenes.length) return;
    setLoading(true);
    const story = { title: "story", scenes };
    fetch(`${API_BASE}/blueprint`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ story, story_id: storyId }),
    })
      .then((r) => r.json())
      .then((d) => { setBlueprint(d); setSelected(d.spatial_nodes[0] ?? null); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [storyId, scenes]);

  function downloadBlueprint() {
    if (!blueprint) return;
    const blob = new Blob([JSON.stringify(blueprint, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url;
    a.download = `${storyId}-engine-blueprint.json`; a.click();
    URL.revokeObjectURL(url);
  }

  if (loading) return (
    <div className="bp-loading"><span className="spinner" /> Generating 3D spatial blueprint…</div>
  );
  if (!blueprint) return (
    <div className="bp-empty">No story loaded. Generate or load a sample first.</div>
  );

  const { stats, world_bounds, spatial_nodes } = blueprint;

  return (
    <div className="blueprint">

      {/* ── Header stats bar ── */}
      <div className="bp-stats-bar">
        <div className="bp-stat"><span className="bp-stat-val">{stats.total_rooms}</span><span className="bp-stat-lbl">Rooms</span></div>
        <div className="bp-stat"><span className="bp-stat-val">{stats.terminal_rooms}</span><span className="bp-stat-lbl">Endings</span></div>
        <div className="bp-stat"><span className="bp-stat-val">{stats.max_depth}</span><span className="bp-stat-lbl">Max Depth</span></div>
        <div className="bp-stat"><span className="bp-stat-val">{stats.total_triggers}</span><span className="bp-stat-lbl">Triggers</span></div>
        <div className="bp-stat"><span className="bp-stat-val">{world_bounds.x_extent}m</span><span className="bp-stat-lbl">World Width</span></div>
        <div className="bp-stat"><span className="bp-stat-val">{world_bounds.z_extent}m</span><span className="bp-stat-lbl">World Depth</span></div>
        <div className="bp-engines">
          {blueprint.engine_formats.map((f, i) => <span key={i} className="bp-engine-chip">{f}</span>)}
        </div>
        <button className="btn btn--secondary bp-dl-btn" onClick={downloadBlueprint}>↓ Export Blueprint</button>
      </div>

      {/* ── View toggle ── */}
      <div className="bp-view-toggle">
        <button className={`bp-view-btn ${view === "map" ? "bp-view-btn--active" : ""}`} onClick={() => setView("map")}>
          ⬡ Spatial Map
        </button>
        <button className={`bp-view-btn ${view === "json" ? "bp-view-btn--active" : ""}`} onClick={() => setView("json")}>
          {"{ }"} Raw Blueprint JSON
        </button>
      </div>

      {view === "map" ? (
        <div className="bp-body">

          {/* ── Node map (SVG top-down view) ── */}
          <div className="bp-map-wrap">
            <SpatialMapSVG nodes={spatial_nodes} selected={selected} onSelect={setSelected} />
          </div>

          {/* ── Node inspector ── */}
          <div className="bp-inspector">
            {selected ? (
              <>
                <div className="bp-node-header">
                  <span className="bp-node-id">{selected.scene_id}</span>
                  <span className="bp-tone-badge" style={{ background: (TONE_COLORS[selected.tone] ?? "#3b82f6") + "22", color: TONE_COLORS[selected.tone] ?? "#3b82f6", border: `1px solid ${TONE_COLORS[selected.tone] ?? "#3b82f6"}` }}>
                    {selected.tone}
                  </span>
                  {selected.is_terminal && <span className="bp-terminal-badge">Terminal</span>}
                </div>
                <div className="bp-room-name">{selected.room_name}</div>

                <div className="bp-section-label">Transform</div>
                <div className="bp-transform-grid">
                  {(["X","Y","Z"] as const).map((axis, i) => (
                    <div key={axis} className="bp-transform-cell">
                      <span className="bp-axis">{axis}</span>
                      <span className="bp-coord">{selected.transform.position[i].toFixed(1)}m</span>
                    </div>
                  ))}
                </div>

                <div className="bp-section-label">Assets to Load</div>
                <div className="bp-asset-list">
                  {selected.assets_to_load.map((a, i) => (
                    <span key={i} className="bp-asset-chip">{a}</span>
                  ))}
                </div>

                {selected.triggers.length > 0 && (
                  <>
                    <div className="bp-section-label">Triggers</div>
                    {selected.triggers.map((t, i) => (
                      <div key={i} className="bp-trigger">
                        <div className="bp-trigger-type">{t.interaction_type}</div>
                        <div className="bp-trigger-detail">→ {t.target_scene} · {t.distance_metres}m · "{t.choice_label.slice(0, 32)}{t.choice_label.length > 32 ? "…" : ""}"</div>
                      </div>
                    ))}
                  </>
                )}
              </>
            ) : (
              <div className="bp-inspector-empty">Click a room to inspect</div>
            )}
          </div>

        </div>
      ) : (
        <div className="bp-json-view">
          <pre>{JSON.stringify(blueprint, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

// ── SVG top-down spatial map ──────────────────────────────────────────────────

function SpatialMapSVG({ nodes, selected, onSelect }: {
  nodes: SpatialNode[];
  selected: SpatialNode | null;
  onSelect: (n: SpatialNode) => void;
}) {
  if (!nodes.length) return null;

  const SCALE = 9;
  const NODE_R = 18;
  const PAD = 40;

  const xs = nodes.map((n) => n.transform.position[0]);
  const zs = nodes.map((n) => n.transform.position[2]);
  const minX = Math.min(...xs); const maxX = Math.max(...xs);
  const minZ = Math.min(...zs); const maxZ = Math.max(...zs);

  const W = (maxX - minX) * SCALE + PAD * 2 + NODE_R * 2;
  const H = (maxZ - minZ) * SCALE + PAD * 2 + NODE_R * 2;

  function cx(x: number) { return (x - minX) * SCALE + PAD + NODE_R; }
  function cy(z: number) { return (z - minZ) * SCALE + PAD + NODE_R; }

  const nodeMap = Object.fromEntries(nodes.map((n) => [n.scene_id, n]));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxHeight: 480, display: "block" }}>
      <rect width={W} height={H} fill="#0f172a" rx={8} />
      {/* Grid lines */}
      {nodes.map((n) =>
        n.triggers.map((t, ti) => {
          const target = nodeMap[t.target_scene];
          if (!target) return null;
          return (
            <line key={`${n.scene_id}-${ti}`}
              x1={cx(n.transform.position[0])} y1={cy(n.transform.position[2])}
              x2={cx(target.transform.position[0])} y2={cy(target.transform.position[2])}
              stroke="#334155" strokeWidth={1.5} strokeDasharray="4 3"
            />
          );
        })
      )}
      {/* Room nodes */}
      {nodes.map((n) => {
        const color = TONE_COLORS[n.tone] ?? "#3b82f6";
        const isSelected = selected?.scene_id === n.scene_id;
        return (
          <g key={n.scene_id} style={{ cursor: "pointer" }} onClick={() => onSelect(n)}>
            <circle
              cx={cx(n.transform.position[0])} cy={cy(n.transform.position[2])}
              r={NODE_R}
              fill={color + (isSelected ? "44" : "22")}
              stroke={color}
              strokeWidth={isSelected ? 2.5 : 1.5}
            />
            {n.is_terminal && (
              <circle cx={cx(n.transform.position[0])} cy={cy(n.transform.position[2])}
                r={NODE_R - 5} fill="none" stroke={color} strokeWidth={1} strokeDasharray="3 2" />
            )}
            <text
              x={cx(n.transform.position[0])} y={cy(n.transform.position[2]) + 4}
              textAnchor="middle" fill={color}
              fontSize={9} fontFamily="monospace" fontWeight={isSelected ? "bold" : "normal"}
            >
              {n.scene_id.replace("scene_", "s")}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
