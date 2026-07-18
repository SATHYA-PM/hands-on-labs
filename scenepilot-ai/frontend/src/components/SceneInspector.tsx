import type { Scene } from "../types";

const TONE_COLORS: Record<string, { bg: string; color: string; border: string }> = {
  tense:   { bg: "#fffbeb", color: "#92400e", border: "#f59e0b" },
  hopeful: { bg: "#f0fdf4", color: "#166534", border: "#22c55e" },
  dark:    { bg: "#f9fafb", color: "#374151", border: "#6b7280" },
  neutral: { bg: "#eff6ff", color: "#1e40af", border: "#3b82f6" },
  playful: { bg: "#faf5ff", color: "#6b21a8", border: "#a855f7" },
};

interface Props {
  scene: Scene | null;
}

export default function SceneInspector({ scene }: Props) {
  if (!scene) {
    return (
      <div className="inspector--empty">
        <div className="inspector--empty-icon">◈</div>
        <p>Click any scene node<br />to inspect its details</p>
      </div>
    );
  }

  const tone = TONE_COLORS[scene.tone] ?? TONE_COLORS.neutral;

  return (
    <div>
      <div className="inspector-header">
        <span className="inspector-id">{scene.id}</span>
        <span
          className="inspector-tone"
          style={{ background: tone.bg, color: tone.color, border: `1px solid ${tone.border}` }}
        >
          {scene.tone}
        </span>
      </div>

      <p className="inspector-text">{scene.text}</p>

      {scene.choices.length > 0 ? (
        <div className="inspector-choices">
          <h4>Choices</h4>
          <ul>
            {scene.choices.map((c, i) => (
              <li key={i}>
                <span className="choice-arrow">→</span>
                <span className="choice-text">{c.text}</span>
                {c.next
                  ? <span className="choice-next">{c.next}</span>
                  : <span className="choice-ending">ending</span>
                }
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="inspector-ending">Terminal scene — story ends here.</div>
      )}
    </div>
  );
}
