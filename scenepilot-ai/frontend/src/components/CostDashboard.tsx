import type { AgentSpan } from "../types";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts";

interface Props {
  spans: AgentSpan[];
  tokenSpend: number;
  tokenCeiling?: number;
}

// Covers all agent label variants the backend can now emit:
//   StoryGeneratorAgent                → full generation pass
//   StoryGeneratorAgent[cycle-repair]  → diff-patch cycle repair pass
//   StoryGeneratorAgent[style-repair]  → diff-patch style repair pass
//   StoryGeneratorAgent[budget-halt]   → aborted due to insufficient budget
const AGENT_COLORS: Record<string, string> = {
  "StoryGeneratorAgent":                    "#3b82f6",
  "StoryGeneratorAgent[cycle-repair]":      "#6366f1",
  "StoryGeneratorAgent[style-repair]":      "#7c3aed",
  "StoryGeneratorAgent[budget-halt]":       "#ef4444",
  "StyleVaultAgent":                        "#a855f7",
  "SandboxValidatorAgent":                  "#f59e0b",
  "GraniteGuardianAgent":                   "#0f62fe",
  "ComplianceAgent":                        "#22c55e",
};

const AGENT_SHORT: Record<string, string> = {
  "StoryGeneratorAgent":                    "Generator",
  "StoryGeneratorAgent[cycle-repair]":      "Generator[cycle✦]",
  "StoryGeneratorAgent[style-repair]":      "Generator[style✦]",
  "StoryGeneratorAgent[budget-halt]":       "Generator[halt]",
  "StyleVaultAgent":                        "Style",
  "SandboxValidatorAgent":                  "Sandbox",
  "GraniteGuardianAgent":                   "Guardian",
  "ComplianceAgent":                        "Compliance",
};

function shortLabel(agent: string): string {
  return AGENT_SHORT[agent] ?? agent.replace("Agent", "");
}

function agentColor(agent: string): string {
  return AGENT_COLORS[agent] ?? "#6b7280";
}

export default function CostDashboard({ spans, tokenSpend, tokenCeiling = 10_000 }: Props) {
  const isDemoSample = tokenSpend === 0 && spans.length === 0;

  const chartData = spans
    .filter((s) => s.duration_ms > 0)
    .map((s) => ({
      name:  shortLabel(s.agent),
      ms:    s.duration_ms,
      color: agentColor(s.agent),
    }));

  const pct = tokenCeiling > 0
    ? Math.min(100, Math.round((tokenSpend / tokenCeiling) * 100))
    : 0;

  const totalDuration = spans.reduce((acc, s) => acc + (s.duration_ms ?? 0), 0);

  // Count all generator invocations (full-gen + repair + halt) then subtract
  // the initial attempt to get the retry count.
  const generatorSpans = spans.filter((s) => s.agent.startsWith("StoryGeneratorAgent"));
  const retries = Math.max(0, generatorSpans.length - 1);

  // Repair passes are a subset of retries that used the diff-patch path.
  // Count both cycle-repair and style-repair spans.
  const cycleRepairPasses = spans.filter((s) => s.agent === "StoryGeneratorAgent[cycle-repair]").length;
  const styleRepairPasses = spans.filter((s) => s.agent === "StoryGeneratorAgent[style-repair]").length;
  const repairPasses = cycleRepairPasses + styleRepairPasses;

  // Budget halt: any span with the budget-halt label signals an aborted run.
  const budgetHalted = spans.some((s) => s.agent === "StoryGeneratorAgent[budget-halt]");

  return (
    <div className="cost-dashboard">
      <h3>Token &amp; Cost Metrics</h3>

      {isDemoSample ? (
        <div className="cost-demo-notice">
          <span className="cost-demo-icon">ℹ</span>
          Demo samples are loaded directly — no LLM pipeline was run.
          Generate a story from a premise to see live token and agent metrics.
        </div>
      ) : (
        <>
          {/* ── Budget-halt warning ── */}
          {budgetHalted && (
            <div className="cost-budget-halt">
              <span className="cost-halt-icon">⊘</span>
              <span>
                <strong>Budget Gate Triggered</strong> — the pipeline was halted
                before a retry because the remaining token balance was insufficient
                for another LLM pass. Raise{" "}
                <code>TOKEN_BUDGET_LIMIT</code> in <code>.env</code> to enable
                full self-healing.
              </span>
            </div>
          )}

          {/* ── Summary cards ── */}
          <div className="cost-summary-row">
            <div className="cost-card">
              <span className="cost-card-value">{tokenSpend.toLocaleString()}</span>
              <span className="cost-card-label">Tokens Used</span>
            </div>
            <div className="cost-card">
              <span className="cost-card-value">{pct}%</span>
              <span className="cost-card-label">Budget Used</span>
            </div>
            <div className="cost-card">
              <span className="cost-card-value">{totalDuration.toLocaleString()}ms</span>
              <span className="cost-card-label">Total Duration</span>
            </div>
            <div className="cost-card">
              <span className="cost-card-value">{retries}</span>
              <span className="cost-card-label">Retries</span>
            </div>
            {cycleRepairPasses > 0 && (
              <div className="cost-card cost-card--repair">
                <span className="cost-card-value">{cycleRepairPasses}</span>
                <span className="cost-card-label">Cycle Repairs</span>
              </div>
            )}
            {styleRepairPasses > 0 && (
              <div className="cost-card cost-card--style-repair">
                <span className="cost-card-value">{styleRepairPasses}</span>
                <span className="cost-card-label">Style Repairs</span>
              </div>
            )}
          </div>

          {/* ── Token budget bar ── */}
          <h4>Token Budget</h4>
          <div className="budget-bar-label">
            <span>{tokenSpend.toLocaleString()} used</span>
            <span>{tokenCeiling.toLocaleString()} ceiling · {pct}%</span>
          </div>
          <div className="budget-bar-track">
            <div
              className={`budget-bar-fill ${pct > 80 ? "budget-bar-fill--warn" : ""} ${budgetHalted ? "budget-bar-fill--halt" : ""}`}
              style={{ width: `${pct}%` }}
            />
          </div>

          {/* ── Agent duration chart ── */}
          {chartData.length > 0 && (
            <>
              <h4>Agent Duration (ms)</h4>
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={chartData} margin={{ left: -10, right: 8 }}>
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => [`${v}ms`, "Duration"]} />
                  <Bar dataKey="ms" radius={[4, 4, 0, 0]}>
                    {chartData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </>
          )}

          {/* ── Agent span table ── */}
          {spans.length > 0 && (
            <>
              <h4>Pipeline Trace</h4>
              <table className="spans-table">
                <thead>
                  <tr>
                    <th>Agent</th><th>Duration</th><th>Tokens</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {spans.map((s, i) => (
                    <tr key={i} className={s.success ? "" : "row--fail"}>
                      <td>
                        {shortLabel(s.agent)}
                        {s.repair_type && s.repair_type !== "none" && (
                          <span className={`repair-badge repair-badge--${s.repair_type}`}>
                            {s.repair_type === "cycle-repair" ? "cycle" : "style"}
                          </span>
                        )}
                      </td>
                      <td>{s.duration_ms}ms</td>
                      <td>{s.tokens != null ? s.tokens.toLocaleString() : "—"}</td>
                      <td>{s.success ? "✓" : "✗"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
    </div>
  );
}
