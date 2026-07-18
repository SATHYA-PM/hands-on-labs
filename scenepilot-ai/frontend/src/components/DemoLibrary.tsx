import { useEffect, useState } from "react";
import type { SampleMeta } from "../types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

const DESCRIPTIONS: Record<string, string> = {
  heist_thriller: "Crime thriller · Circular loop seeded",
  fantasy_rpg:    "Fantasy RPG · Dead-end node seeded",
  product_launch: "Marketing · Tone drift seeded",
  space_escape:   "Sci-Fi · Infinite retry loop seeded",
  edu_quiz_tree:  "Educational · Schema violation seeded",
};

interface Props {
  onSelect: (name: string) => void;
  selectedSample: string | null;
  isLoading: boolean;
}

export default function DemoLibrary({ onSelect, selectedSample, isLoading }: Props) {
  const [samples, setSamples] = useState<SampleMeta[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/samples`)
      .then((r) => r.json())
      .then((d) => setSamples(d.samples ?? []))
      .catch(() => setSamples([]))
      .finally(() => setFetching(false));
  }, []);

  if (fetching) return <p className="demo-loading">Loading samples…</p>;

  return (
    <div>
      <div className="demo-section-title">Demo Samples</div>
      <p className="demo-subtitle">Click a sample to pre-fill the form, then hit Generate Story.</p>
      <div className="demo-grid">
        {samples.map((s) => {
          const isSelected = selectedSample === s.name;
          return (
            <button
              key={s.name}
              type="button"
              className={`demo-card${isSelected ? " demo-card--selected" : ""}`}
              onClick={() => onSelect(s.name)}
              disabled={isLoading}
            >
              <div className="demo-card-row">
                <span className="demo-name">{s.name.replace(/_/g, " ")}</span>
                {isSelected && <span className="demo-selected-badge">Selected</span>}
              </div>
              <span className="demo-desc">{DESCRIPTIONS[s.name] ?? s.filename}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
