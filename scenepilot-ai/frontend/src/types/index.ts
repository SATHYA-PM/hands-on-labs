export interface Choice {
  text: string;
  next: string | null;
}

export interface Scene {
  id: string;
  text: string;
  tone: "tense" | "hopeful" | "dark" | "neutral" | "playful";
  choices: Choice[];
}

export interface Story {
  title: string;
  genre: string;
  scenes: Scene[];
}

export interface ValidationResult {
  passed: boolean;
  issues: string[];
  cycles_detected: number;
  schema_errors: string[];
  style_violations: string[];
  structural_warnings?: string[];
}

export interface AgentSpan {
  agent: string;
  duration_ms: number;
  tokens?: number;
  violations?: number;
  cycles?: number;
  schema_errors?: number;
  passed?: boolean;
  success: boolean;
  fingerprint?: string;
  error?: string;
  // Repair / budget-gate observability fields (populated by story_generator_node)
  repair_mode?: boolean;
  tokens_used?: number;   // cumulative spend including this span
  token_ceiling?: number; // ceiling value at time of this span
}

export interface GenerateResponse {
  story_id: string;
  approved: boolean;
  title: string | null;
  scenes: Scene[] | null;
  validation: ValidationResult | null;
  agent_spans: AgentSpan[];
  token_spend: number;
  token_ceiling: number;
  error: string | null;
}

export type Genre = "thriller" | "fantasy" | "sci-fi" | "educational" | "marketing";

export interface SampleMeta {
  name: string;
  filename: string;
  url: string;
}

export type PipelineStatus = "idle" | "generating" | "validating" | "done" | "error";

/**
 * Minimum number of scenes required for a story to be considered structurally
 * complete. Must be kept in sync with MIN_SCENES in sandbox/validator.py:13.
 * If that constant changes, update this value to match.
 */
export const MIN_SCENES = 6;
