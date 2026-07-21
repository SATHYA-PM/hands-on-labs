import type { ValidationResult, AgentSpan } from "../types";

// Structured FAISS advisory entry returned by style_vault_agent
interface AdvisoryEntry {
  scene_id: string;
  score: number;
  rule: string;
  message: string;
}

interface Props {
  validation: ValidationResult | null;
  agentSpans: AgentSpan[];
  tokenSpend: number;
  approved: boolean;
  error?: string | null;
}

const AGENT_NAMES: Record<string, string> = {
  "StoryGeneratorAgent":                       "Story Generator",
  "StoryGeneratorAgent[repair]":               "Story Generator (Repair)",
  "StoryGeneratorAgent[budget-halt]":          "Story Generator (Budget Halt)",
  "StoryGeneratorAgent[cycle-repair]":         "Story Generator (Cycle Repair)",
  "StoryGeneratorAgent[schema-repair]":        "Story Generator (Schema Repair)",
  "StoryGeneratorAgent[structural-repair]":    "Story Generator (Structural Repair)",
  "StoryGeneratorAgent[style-repair]":         "Story Generator (Style Repair)",
  "StyleVaultAgent":                           "Style Vault",
  "SandboxValidatorAgent":                     "Sandbox Validator",
  "GraniteGuardianAgent":                      "IBM Granite Guardian",
  "ComplianceAgent":                           "Compliance",
};

export default function ValidationReport({ validation, agentSpans, tokenSpend, approved, error }: Props) {
  const structuralIssues  = validation?.structural_warnings ?? [];
  const cycleIssues       = validation?.issues.filter(i => i.startsWith("Cycle")) ?? [];
  const schemaIssues      = validation?.schema_errors ?? [];
  // Blocking style violations = tone mismatches only (FAISS advisory excluded)
  const styleIssues       = validation?.style_violations ?? [];
  // Advisory = FAISS similarity scores — shown as info, never blocks approval
  const rawAdvisory       = (validation as any)?.style_advisory_structured ?? [];
  // Fall back to flat strings if structured data isn't present
  const flatAdvisory: string[] = (validation as any)?.style_advisory ?? [];
  const hasStructured     = rawAdvisory.length > 0;
  const totalIssues       = schemaIssues.length + cycleIssues.length + styleIssues.length + structuralIssues.length;

  // The real rejection reason is structural/schema/cycle — make it explicit
  const rejectionReasons: string[] = [
    ...(cycleIssues.length > 0       ? [`${cycleIssues.length} cycle(s) detected`] : []),
    ...(schemaIssues.length > 0      ? [`${schemaIssues.length} schema error(s)`] : []),
    ...(structuralIssues.length > 0  ? [`${structuralIssues.length} structural issue(s) (orphaned/dangling scenes)`] : []),
    ...(styleIssues.length > 0       ? [`${styleIssues.length} tone mismatch(es)`] : []),
  ];

  // Classify backend error type for precise banner + error-box display.
  // Order matters: check most-specific prefixes first.
  const isBudgetHalt    = error?.startsWith("BUDGET HALT");
  const isPreFlight     = error?.startsWith("PRE-FLIGHT");
  const isExhausted     = error?.startsWith("BUDGET EXHAUSTED");
  const isQuotaError    = error?.includes("PROVIDER QUOTA EXHAUSTED") || error?.includes("API quota exhausted");
  const isTruncated     = error?.startsWith("Generation Truncated");

  return (
    <div className="report">

      {/* ── Status banner ── */}
      <div className={`report-banner ${approved ? "report-banner--pass" : "report-banner--fail"}`}>
        {approved
          ? "✓ Approved — All quality gates passed"
          : isBudgetHalt  ? "⊘ Budget Gate Triggered — Pipeline halted mid-run, insufficient token balance for next pass"
          : isPreFlight   ? "✗ Pre-flight Rejected — Premise too large for active token ceiling"
          : isExhausted   ? "✗ Budget Exhausted — Story exceeded token ceiling mid-generation"
          : isQuotaError  ? "✗ API Quota Exhausted — Both LLM providers are rate-limited"
          : isTruncated   ? "✗ Generation Truncated — LLM response cut off mid-JSON"
          : rejectionReasons.length > 0
            ? `✗ Rejected — ${rejectionReasons.join(", ")}`
            : `✗ Rejected — ${totalIssues} issue${totalIssues !== 1 ? "s" : ""} detected`}
      </div>

      {/* ── Backend error detail box ── */}
      {error && !approved && (
        <div className="report-error-box">
          <strong>
            {isBudgetHalt  ? "⊘ Mid-Pipeline Budget Gate" :
             isPreFlight   ? "⊘ Pre-flight Check Failed" :
             isExhausted   ? "◑ Token Budget Exhausted" :
             isQuotaError  ? "↺ API Rate Limit Reached" :
             isTruncated   ? "⚠ Generation Truncated" :
                             "✗ Pipeline Error"}
          </strong>
          <p>{error}</p>
        </div>
      )}

      {/* ── Metric tiles ── */}
      {validation && (
        <div className="report-metrics">
          <Metric
            label="Cycles"
            value={validation.cycles_detected}
            warn={validation.cycles_detected > 0}
            icon="↺"
          />
          <Metric
            label="Schema Errors"
            value={schemaIssues.length}
            warn={schemaIssues.length > 0}
            icon="⊘"
          />
          <Metric
            label="Tone Violations"
            value={styleIssues.length}
            warn={styleIssues.length > 0}
            icon="◐"
          />
          <Metric
            label="Style Advisory"
            value={hasStructured ? rawAdvisory.length : flatAdvisory.length}
            warn={false}
            icon="ℹ"
          />
          <Metric
            label="Structural"
            value={structuralIssues.length}
            warn={structuralIssues.length > 0}
            icon="⬡"
          />
          <Metric
            label="Tokens Used"
            value={tokenSpend}
            warn={false}
            icon="◑"
          />
        </div>
      )}

      {/* ── Issue groups ── */}
      {cycleIssues.length > 0 && (
        <IssueGroup title="Cycle / Loop Errors" color="#ef4444" issues={cycleIssues} />
      )}
      {schemaIssues.length > 0 && (
        <IssueGroup title="Schema Errors" color="#f59e0b" issues={schemaIssues} />
      )}
      {structuralIssues.length > 0 && (
        <IssueGroup title="Structural Issues" color="#8b5cf6" issues={structuralIssues} />
      )}
      {styleIssues.length > 0 && (
        <IssueGroup title="Tone Violations (Blocking)" color="#f59e0b" issues={styleIssues} />
      )}
      {hasStructured && (
        <FaissAdvisory entries={rawAdvisory} />
      )}
      {!hasStructured && flatAdvisory.length > 0 && (
        <IssueGroup title="Style Advisory (FAISS — Non-Blocking)" color="#94a3b8" issues={flatAdvisory} />
      )}

      {/* ── All-clear message ── */}
      {approved && (
        <div className="report-allclear">
          All checks passed — story is production ready.
        </div>
      )}

      {/* ── Agent pipeline trace ── */}
      {agentSpans.length > 0 && (
        <div className="report-section">
          <h4>Agent Pipeline Trace</h4>
          <table className="spans-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Duration</th>
                <th>Status</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {agentSpans.map((span, i) => (
                <tr key={i} className={span.success ? "" : "row--fail"}>
                  <td>{AGENT_NAMES[span.agent] ?? span.agent}</td>
                  <td>{span.duration_ms}ms</td>
                  <td style={{ color: span.success ? "#16a34a" : "#dc2626", fontWeight: 700 }}>
                    {span.success ? "✓" : "✗"}
                  </td>
                  <td className="span-notes">
                    {span.tokens      != null && <span>{span.tokens.toLocaleString()} tokens  </span>}
                    {span.violations  != null && <span>{span.violations} violations  </span>}
                    {span.cycles      != null && <span>{span.cycles} cycles  </span>}
                    {span.schema_errors != null && span.schema_errors > 0 && <span>{span.schema_errors} schema errors  </span>}
                    {span.repair_mode && <span className="span-tag span-tag--repair">repair</span>}
                    {span.fingerprint && <span className="fp-badge">fp: {span.fingerprint}</span>}
                    {span.error && <span className="span-error" title={span.error}>⚠ {span.error.slice(0, 80)}{span.error.length > 80 ? "…" : ""}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Metric({ label, value, warn, icon }: { label: string; value: number; warn: boolean; icon: string }) {
  return (
    <div className={`metric ${warn ? "metric--warn" : ""}`}>
      <span className="metric-icon">{icon}</span>
      <span className="metric-value">{value.toLocaleString()}</span>
      <span className="metric-label">{label}</span>
    </div>
  );
}

function IssueGroup({ title, color, issues }: { title: string; color: string; issues: string[] }) {
  return (
    <div className="report-section">
      <h4 style={{ color }}>{title}</h4>
      <ul className="issues-list">
        {issues.map((issue, i) => (
          <li key={i} style={{ borderLeftColor: color }}>{issue}</li>
        ))}
      </ul>
    </div>
  );
}

function FaissAdvisory({ entries }: { entries: AdvisoryEntry[] }) {
  const threshold = 0.35;
  // Sort worst-first (lowest score first)
  const sorted = [...entries].sort((a, b) => a.score - b.score);
  return (
    <div className="report-section">
      <h4 style={{ color: "#94a3b8" }}>
        Style Advisory — FAISS Similarity Scores
        <span style={{ fontWeight: 400, fontSize: "0.8em", marginLeft: 8, color: "#94a3b8" }}>
          (non-blocking — shown for diagnostics only)
        </span>
      </h4>
      <div style={{ fontSize: "0.78em", color: "#57606a", marginBottom: 8 }}>
        Threshold: {threshold} &nbsp;·&nbsp; Green ≥ 0.25 &nbsp;·&nbsp; Amber 0.15–0.25 &nbsp;·&nbsp; Red &lt; 0.15
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82em" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #e5e7eb", textAlign: "left", color: "#57606a" }}>
            <th style={{ padding: "4px 8px", width: 100 }}>Scene</th>
            <th style={{ padding: "4px 8px", width: 60 }}>Score</th>
            <th style={{ padding: "4px 8px" }}>Score Bar</th>
            <th style={{ padding: "4px 8px" }}>Nearest Rule</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((e, i) => {
            const pct = Math.round(e.score * 100);
            const color = e.score >= 0.25 ? "#16a34a" : e.score >= 0.15 ? "#d97706" : "#dc2626";
            return (
              <tr key={i} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: "4px 8px", fontFamily: "monospace", color: "#1f2328" }}>{e.scene_id}</td>
                <td style={{ padding: "4px 8px", color, fontWeight: 700 }}>{e.score.toFixed(3)}</td>
                <td style={{ padding: "4px 8px", width: 160 }}>
                  <div style={{ background: "#e5e7eb", borderRadius: 4, height: 8, width: 140 }}>
                    <div style={{ background: color, borderRadius: 4, height: 8, width: `${Math.min(pct / threshold * 100, 100)}%`, maxWidth: "100%" }} />
                  </div>
                </td>
                <td style={{ padding: "4px 8px", color: "#57606a", overflow: "hidden", whiteSpace: "nowrap", maxWidth: 280, textOverflow: "ellipsis" }}
                    title={e.rule}>
                  {e.rule}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
