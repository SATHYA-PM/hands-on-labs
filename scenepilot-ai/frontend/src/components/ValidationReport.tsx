import type { ValidationResult, AgentSpan } from "../types";

interface Props {
  validation: ValidationResult | null;
  agentSpans: AgentSpan[];
  tokenSpend: number;
  approved: boolean;
  error?: string | null;
}

const AGENT_NAMES: Record<string, string> = {
  "StoryGeneratorAgent":              "Story Generator",
  "StoryGeneratorAgent[repair]":      "Story Generator (Repair)",
  "StoryGeneratorAgent[budget-halt]": "Story Generator (Budget Halt)",
  "StyleVaultAgent":                  "Style Vault",
  "SandboxValidatorAgent":            "Sandbox Validator",
  "ComplianceAgent":                  "Compliance",
};

export default function ValidationReport({ validation, agentSpans, tokenSpend, approved, error }: Props) {
  const structuralIssues  = validation?.structural_warnings ?? [];
  const cycleIssues       = validation?.issues.filter(i => i.startsWith("Cycle")) ?? [];
  const schemaIssues      = validation?.schema_errors ?? [];
  const styleIssues       = validation?.style_violations ?? [];
  const totalIssues       = (validation?.issues.length ?? 0);

  // Classify backend error type for precise banner + error-box display.
  // Order matters: check most-specific prefixes first.
  const isBudgetHalt  = error?.startsWith("BUDGET HALT");
  const isPreFlight   = error?.startsWith("PRE-FLIGHT");
  const isExhausted   = error?.startsWith("BUDGET EXHAUSTED");
  const isQuotaError  = error?.includes("API quota exhausted");
  const isTruncated   = error?.startsWith("Generation Truncated");

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
            label="Style Violations"
            value={styleIssues.length}
            warn={styleIssues.length > 0}
            icon="◐"
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
        <IssueGroup title="Style Violations" color="#06b6d4" issues={styleIssues} />
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
