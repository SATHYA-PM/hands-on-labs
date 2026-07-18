import React, { useState, useEffect } from "react";
import type { Genre } from "../types";

interface ExternalValues {
  premise: string;
  genre: Genre;
  tone: number;
}

interface Props {
  onGenerate: (premise: string, genre: Genre, tone: number) => void;
  isLoading: boolean;
  onPremiseChange?: (len: number) => void;
  externalValues?: ExternalValues | null;
  onUserEdit?: () => void;   // called when user manually edits premise
}

const GENRES: Genre[] = ["thriller", "fantasy", "sci-fi", "educational", "marketing"];

const PLACEHOLDER: Record<Genre, string> = {
  thriller:    "A disgraced detective receives a coded message from a serial killer who should be dead.",
  fantasy:     "A cartographer discovers the blank edges of her map are not unmapped — they are erased.",
  "sci-fi":    "The last maintenance robot on a derelict space station receives a distress call from Earth.",
  educational: "A water droplet named Pip takes you on a journey through the complete water cycle.",
  marketing:   "You have 24 hours to launch your app before a competitor beats you to market.",
};

export default function PremiseInput({ onGenerate, onPremiseChange, externalValues, onUserEdit }: Props) {
  const [premise, setPremise] = useState("");
  const [genre,   setGenre]   = useState<Genre>("thriller");
  const [tone,    setTone]    = useState(0.5);

  // When a demo sample is selected, inject its values into the form fields.
  useEffect(() => {
    if (!externalValues) return;
    setPremise(externalValues.premise);
    setGenre(externalValues.genre);
    setTone(externalValues.tone);
    onPremiseChange?.(externalValues.premise.length);
  }, [externalValues]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (premise.trim().length < 10) return;
    onGenerate(premise.trim(), genre, tone);
  };

  const handlePremiseChange = (val: string) => {
    setPremise(val);
    onPremiseChange?.(val.length);
    onUserEdit?.();   // user typed → clear any locked demo sample
  };

  const toneLabel =
    tone <= 0.25 ? "Dark" :
    tone <= 0.5  ? "Tense" :
    tone <= 0.75 ? "Hopeful" : "Playful";

  return (
    <form id="premise-form" onSubmit={handleSubmit} className="premise-form">

      <div>
        <div className="form-section-label">Genre</div>
        <div className="genre-pills">
          {GENRES.map((g) => (
            <button
              key={g}
              type="button"
              className={`pill ${genre === g ? "pill--active" : ""}`}
              onClick={() => setGenre(g)}
            >
              {g}
            </button>
          ))}
        </div>
      </div>

      <div>
        <div className="form-section-label">Premise</div>
        <textarea
          rows={4}
          value={premise}
          onChange={(e) => handlePremiseChange(e.target.value)}
          placeholder={PLACEHOLDER[genre]}
          maxLength={2000}
          required
        />
        <div className="char-count">{premise.length} / 2000</div>
      </div>

      <div>
        <div className="tone-row">
          <span className="tone-label">Tone</span>
          <span className="tone-badge">{toneLabel}</span>
        </div>
        <input
          type="range"
          min={0} max={1} step={0.05}
          value={tone}
          onChange={(e) => setTone(parseFloat(e.target.value))}
        />
        <div className="tone-ends"><span>Dark</span><span>Playful</span></div>
      </div>

    </form>
  );
}
