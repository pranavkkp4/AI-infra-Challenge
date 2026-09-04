import { Link } from "react-router-dom";

import { useApi } from "../api";
import { EvidenceIds, SectionHeading } from "../components/DataDisplay";
import { StatePanel } from "../components/StatePanel";
import { compactNumber, label, percent, riskBand } from "../format";
import type { DashboardData, DashboardMetrics } from "../types";

interface MetricItem {
  name: string;
  value: string;
  note: string;
  tone: string;
}

function metricItems(metrics: DashboardMetrics): MetricItem[] {
  return [
    { name: "Work orders", value: compactNumber(metrics.total_work_orders), note: "deduplicated jobs", tone: "neutral" },
    { name: "Assets observed", value: String(metrics.unique_assets), note: "typed asset keys", tone: "neutral" },
    { name: "Recurring episodes", value: String(metrics.recurring_incidents), note: percent(metrics.repeat_incident_rate), tone: "alert" },
    { name: "High-risk assets", value: String(metrics.high_risk_assets), note: "score 65 or above", tone: "alert" },
    { name: "Pending review", value: String(metrics.human_review_count), note: "below threshold", tone: "review" },
    { name: "Mean confidence", value: percent(metrics.average_confidence), note: "deterministic score", tone: "evidence" },
  ];
}

function MetricStrip({ metrics }: { metrics: DashboardMetrics }) {
  return <section className="metric-strip">{metricItems(metrics).map((metric) => (
    <article className={`metric-card ${metric.tone}`} key={metric.name}>
      <span>{metric.name}</span><strong>{metric.value}</strong><small>{metric.note}</small>
    </article>
  ))}</section>;
}

function IncidentChart({ data }: { data: DashboardData["incidents_over_time"] }) {
  const recent = data.slice(-20);
  const max = Math.max(...recent.map((item) => item.incidents), 1);
  return (
    <div className="bar-chart" aria-label="Incidents over time">
      {recent.map((item) => <div className="bar-column" key={item.period} title={`${item.period}: ${item.incidents}`}>
        <span style={{ height: `${Math.max(8, item.incidents / max * 100)}%` }} />
        <small>{item.period.slice(2, 4)}'{item.period.slice(5)}</small>
      </div>)}
    </div>
  );
}

function RiskBoard({ data }: { data: DashboardData["high_risk_assets"] }) {
  return <div className="risk-board">{data.map((asset, index) => (
    <Link to={`/assets?asset=${encodeURIComponent(asset.asset_key)}`} key={asset.asset_key}>
      <span className="rank">{String(index + 1).padStart(2, "0")}</span>
      <strong>{asset.asset_key}</strong>
      <span className="risk-track"><i style={{ width: `${asset.risk_score}%` }} /></span>
      <b className={riskBand(asset.risk_score)}>{asset.risk_score}</b>
    </Link>
  ))}</div>;
}

function IssueMix({ data }: { data: DashboardData["issue_distribution"] }) {
  const total = data.reduce((sum, item) => sum + item.value, 0);
  return <div className="issue-mix">{data.slice(0, 7).map((item) => (
    <div key={item.name}><span>{label(item.name)}</span><i><b style={{ width: `${item.value / total * 100}%` }} /></i><strong>{item.value}</strong></div>
  ))}</div>;
}

function PatternLedger({ patterns }: { patterns: DashboardData["patterns"] }) {
  return <div className="pattern-ledger">{patterns.map((pattern, index) => (
    <article key={pattern.title}>
      <span className="pattern-index">P-{String(index + 1).padStart(2, "0")}</span>
      <div><strong>{pattern.title}</strong><small>{pattern.incident_count} grouped episodes</small><EvidenceIds identifiers={pattern.supporting_work_orders} /></div>
    </article>
  ))}</div>;
}

function Dashboard({ data }: { data: DashboardData }) {
  return <div className="page-stack reveal">
    <section className="page-intro"><div><span className="eyebrow">SYSTEM-WIDE POSTURE</span><h1>Infrastructure signals,<br /><em>made operational.</em></h1></div><p>Historical maintenance records grouped into evidence-backed episodes. Every recommendation remains traceable to source work orders.</p></section>
    <MetricStrip metrics={data.metrics} />
    <section className="dashboard-grid">
      <article className="panel chart-panel"><SectionHeading data={{ index: "A", title: "Incident cadence", note: "First-seen episodes by month" }} /><IncidentChart data={data.incidents_over_time} /></article>
      <article className="panel"><SectionHeading data={{ index: "B", title: "Asset risk register", note: "Transparent deterministic score" }} /><RiskBoard data={data.high_risk_assets} /></article>
      <article className="panel"><SectionHeading data={{ index: "C", title: "Issue composition", note: "Canonical incident families" }} /><IssueMix data={data.issue_distribution} /></article>
      <article className="panel patterns-panel"><SectionHeading data={{ index: "D", title: "Recurring pattern ledger", note: "Work-order citations shown in teal" }} /><PatternLedger patterns={data.patterns} /></article>
    </section>
  </div>;
}

export function DashboardPage() {
  const result = useApi<DashboardData>("/dashboard");
  if (result.loading) return <StatePanel state="loading" />;
  if (result.error) return <StatePanel state="error" message={result.error} retry={result.reload} />;
  if (!result.data) return <StatePanel state="empty" />;
  return <Dashboard data={result.data} />;
}
