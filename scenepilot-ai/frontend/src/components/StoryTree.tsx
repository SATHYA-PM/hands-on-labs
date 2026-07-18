import React, { useCallback, useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  BaseEdge,
  EdgeLabelRenderer,
  getStraightPath,
  useNodesState,
  useEdgesState,
  type NodeProps,
  type EdgeProps,
  type Node,
  type Edge,
} from "reactflow";
import "reactflow/dist/style.css";
import type { Scene } from "../types";

// ── Tone colour map ───────────────────────────────────────────────────────────
const TONE_COLORS: Record<string, { border: string; bg: string; text: string }> = {
  tense:   { border: "#f59e0b", bg: "#fffbeb", text: "#92400e" },
  hopeful: { border: "#22c55e", bg: "#f0fdf4", text: "#166534" },
  dark:    { border: "#6b7280", bg: "#f9fafb", text: "#374151" },
  neutral: { border: "#3b82f6", bg: "#eff6ff", text: "#1e40af" },
  playful: { border: "#a855f7", bg: "#faf5ff", text: "#6b21a8" },
};

const DEFAULT_TONE = { border: "#3b82f6", bg: "#eff6ff", text: "#1e40af" };

// ── Custom scene node ─────────────────────────────────────────────────────────
function SceneNode({ data, selected }: NodeProps) {
  const colors = TONE_COLORS[data.tone] ?? DEFAULT_TONE;

  return (
    <div
      style={{
        background: colors.bg,
        border: `2px solid ${selected ? colors.border : colors.border + "99"}`,
        borderRadius: 10,
        padding: "10px 14px",
        width: 210,
        boxShadow: selected
          ? `0 0 0 3px ${colors.border}44, 0 4px 12px rgba(0,0,0,0.12)`
          : "0 2px 6px rgba(0,0,0,0.07)",
        transition: "box-shadow 0.15s, border-color 0.15s",
        cursor: "pointer",
        position: "relative",
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        style={{ background: colors.border, width: 8, height: 8, border: "2px solid #fff" }}
      />

      {/* Scene ID + tone badge */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{
          fontFamily: "monospace",
          fontSize: 11,
          fontWeight: 700,
          color: colors.text,
          background: colors.border + "22",
          padding: "1px 6px",
          borderRadius: 4,
        }}>
          {data.id}
        </span>
        {data.isEnding && (
          <span style={{ fontSize: 10, color: "#9ca3af", fontStyle: "italic" }}>ending</span>
        )}
      </div>

      {/* Scene text — clamp to 3 lines */}
      <p style={{
        fontSize: 11.5,
        color: "#374151",
        lineHeight: 1.55,
        margin: 0,
        display: "-webkit-box",
        WebkitLineClamp: 3,
        WebkitBoxOrient: "vertical",
        overflow: "hidden",
      }}>
        {data.text}
      </p>

      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: colors.border, width: 8, height: 8, border: "2px solid #fff" }}
      />
    </div>
  );
}

// ── Custom edge with floating label chip ──────────────────────────────────────
function LabelledEdge({
  id, sourceX, sourceY, targetX, targetY, label, selected,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getStraightPath({ sourceX, sourceY, targetX, targetY });

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: selected ? "#3b82f6" : "#cbd5e1",
          strokeWidth: selected ? 2 : 1.5,
        }}
        markerEnd="url(#arrow)"
      />
      {label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "none",
              zIndex: 10,
            }}
          >
            <span style={{
              display: "inline-block",
              background: "#ffffff",
              border: "1px solid #e2e8f0",
              borderRadius: 5,
              padding: "2px 7px",
              fontSize: 10,
              color: "#475569",
              fontWeight: 500,
              maxWidth: 140,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
            }}>
              {label as string}
            </span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const nodeTypes = { scene: SceneNode };
const edgeTypes = { labelled: LabelledEdge };

// ── BFS layout ────────────────────────────────────────────────────────────────
const NODE_W   = 210;
const NODE_H   = 110;   // approximate rendered height
const X_GAP    = 60;    // horizontal gap between nodes on same level
const Y_GAP    = 90;    // vertical gap between levels

function layoutScenes(scenes: Scene[]): { nodes: Node[]; edges: Edge[] } {
  if (!scenes.length) return { nodes: [], edges: [] };

  const sceneMap = new Map(scenes.map((s) => [s.id, s]));

  // BFS to assign levels
  const levels = new Map<string, number>();
  const queue: string[] = [scenes[0].id];
  levels.set(scenes[0].id, 0);

  while (queue.length) {
    const id = queue.shift()!;
    const scene = sceneMap.get(id);
    if (!scene) continue;
    for (const choice of scene.choices) {
      if (choice.next && !levels.has(choice.next)) {
        levels.set(choice.next, (levels.get(id) ?? 0) + 1);
        queue.push(choice.next);
      }
    }
  }

  // Assign any orphaned nodes a level after their first inbound parent
  for (const scene of scenes) {
    if (!levels.has(scene.id)) levels.set(scene.id, 0);
  }

  // Group by level
  const byLevel = new Map<number, string[]>();
  for (const [id, lvl] of levels) {
    if (!byLevel.has(lvl)) byLevel.set(lvl, []);
    byLevel.get(lvl)!.push(id);
  }

  // X position: centre each level's nodes around x=0
  const nodePositions = new Map<string, { x: number; y: number }>();
  for (const [lvl, ids] of byLevel) {
    const totalW = ids.length * NODE_W + (ids.length - 1) * X_GAP;
    const startX = -totalW / 2;
    ids.forEach((id, i) => {
      nodePositions.set(id, {
        x: startX + i * (NODE_W + X_GAP),
        y: lvl * (NODE_H + Y_GAP),
      });
    });
  }

  const nodes: Node[] = scenes.map((scene) => {
    const pos = nodePositions.get(scene.id) ?? { x: 0, y: 0 };
    return {
      id: scene.id,
      type: "scene",
      position: pos,
      data: {
        id: scene.id,
        text: scene.text,
        tone: scene.tone,
        isEnding: scene.choices.length === 0,
      },
    };
  });

  const edges: Edge[] = [];
  for (const scene of scenes) {
    for (let i = 0; i < scene.choices.length; i++) {
      const choice = scene.choices[i];
      if (!choice.next) continue;
      const label = choice.text.length > 32 ? choice.text.slice(0, 30) + "…" : choice.text;
      edges.push({
        id: `${scene.id}→${choice.next}-${i}`,
        source: scene.id,
        target: choice.next,
        type: "labelled",
        label,
      });
    }
  }

  return { nodes, edges };
}

// ── Arrow marker definition ───────────────────────────────────────────────────
function ArrowMarker() {
  return (
    <svg style={{ position: "absolute", width: 0, height: 0 }}>
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L0,6 L8,3 z" fill="#cbd5e1" />
        </marker>
      </defs>
    </svg>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
interface Props {
  scenes: Scene[];
  onSelectScene: (scene: Scene) => void;
  selectedId?: string;
}

export default function StoryTree({ scenes, onSelectScene, selectedId }: Props) {
  const { nodes: initNodes, edges: initEdges } = useMemo(
    () => layoutScenes(scenes),
    [scenes]
  );

  const [nodes, , onNodesChange] = useNodesState(initNodes);
  const [edges, , onEdgesChange] = useEdgesState(initEdges);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const scene = scenes.find((s) => s.id === node.id);
      if (scene) onSelectScene(scene);
    },
    [scenes, onSelectScene]
  );

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <ArrowMarker />
      <ReactFlow
        nodes={nodes.map((n) => ({ ...n, selected: n.id === selectedId }))}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.18, maxZoom: 1.1 }}
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#e2e8f0" gap={22} size={1} />
        <Controls
          showInteractive={false}
          style={{ bottom: 12, left: 12 }}
        />
        <MiniMap
          nodeColor={(n) => {
            const tone = (n.data as { tone?: string }).tone ?? "neutral";
            return TONE_COLORS[tone]?.border ?? "#3b82f6";
          }}
          nodeStrokeWidth={1}
          nodeStrokeColor="rgba(255,255,255,0.8)"
          zoomable
          pannable
          maskColor="rgba(240,242,245,0.6)"
          style={{ top: 12, right: 12, width: 120, height: 80, borderRadius: 6 }}
        />
      </ReactFlow>

      {/* Tone legend — absolute over the canvas */}
      <div className="tree-legend">
        {Object.entries(TONE_COLORS).map(([tone, c]) => (
          <span key={tone} className="legend-item">
            <span className="legend-dot" style={{ background: c.border }} />
            {tone}
          </span>
        ))}
      </div>
    </div>
  );
}
