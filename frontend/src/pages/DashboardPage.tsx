import { Link } from "react-router-dom";

import { useApi } from "../api";
import { EvidenceIds, InlineEmpty, SectionHeading } from "../components/DataDisplay";
import { StatePanel } from "../components/StatePanel";
import { compactNumber, days, label, percent, riskBand } from "../format";
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
    { name: "High-risk equipment", value: String(metrics.high_risk_assets), note: "score 65 or above", tone: "alert" },
    { name: "Pending review", value: String(metrics.human_review_count), note: "below threshold", tone: "review" },
    { name: "Mean confidence", value: percent(metrics.average_confidence), note: "evidence score", tone: "evidence" },
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
  if (!recent.length) return <InlineEmpty message="No incident cadence is available for this dataset." />;
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
  if (!data.length) return <InlineEmpty message="No equipment currently meets the high-risk threshold." />;
  return <div className="risk-board">{data.map((asset, index) => (
    <Link to={`/assets?asset=${encodeURIComponent(asset.asset_key)}&class=${asset.asset_class}`} key={asset.asset_key}>
      <span className="rank">{String(index + 1).padStart(2, "0")}</span>
      <strong>{asset.asset_key}</strong>
      <span className="risk-track"><i style={{ width: `${asset.risk_score}%` }} /></span>
      <b className={riskBand(asset.risk_score)}>{asset.risk_score}</b>
    </Link>
  ))}</div>;
}

function IssueMix({ data }: { data: DashboardData["issue_distribution"] }) {
  const total = data.reduce((sum, item) => sum + item.value, 0);
  if (!data.length || total === 0) return <InlineEmpty message="Issue-family composition is not available." />;
  return <div className="issue-mix">{data.slice(0, 7).map((item) => (
    <div key={item.name}><span>{label(item.name)}</span><i><b style={{ width: `${item.value / total * 100}%` }} /></i><strong>{item.value}</strong></div>
  ))}</div>;
}

function PatternLedger({ patterns }: { patterns: DashboardData["patterns"] }) {
  if (!patterns.length) return <InlineEmpty message="No recurring patterns have cleared the evidence gate." />;
  return <div className="pattern-ledger">{patterns.map((pattern, index) => (
    <article key={pattern.title}>
      <span className="pattern-index">P-{String(index + 1).padStart(2, "0")}</span>
      <div><strong>{pattern.title}</strong><small>{pattern.incident_count} grouped episodes</small><EvidenceIds identifiers={pattern.supporting_work_orders} /></div>
    </article>
  ))}</div>;
}

function OperationalPosture({ metrics }: { metrics: DashboardMetrics }) {
  const recommendedIntervals = metrics.pm_interval_recommendations ?? 0;
  const intervalPosture = recommendedIntervals
    ? `${recommendedIntervals} proposed`
    : "No interval proposed";
  return (
    <section className="signal-strip" aria-label="Operational posture">
      <article><span>Observed repeat interval</span><strong>{days(metrics.mean_time_between_repeats)}</strong><small>Historical spacing, not a PM prescription</small></article>
      <article><span>Resolution signal</span><strong>{metrics.issue_resolution_rate === null ? "Not available" : percent(metrics.issue_resolution_rate)}</strong><small>Known-resolution episodes only</small></article>
      <article><span>PM interval recommendation</span><strong className={recommendedIntervals ? "signal-ready" : "signal-hold"}>{intervalPosture}</strong><small>{metrics.pm_interval_abstentions ?? 0} episode(s) withheld; validate locally before authorization</small></article>
    </section>
  );
}

function Dashboard({ data }: { data: DashboardData }) {
  return <div className="page-stack reveal">
    <section className="page-intro"><div><span className="eyebrow">SYSTEM-WIDE POSTURE</span><span className="dataset-label">{data.dataset_label}</span><h1>Infrastructure signals,<br /><em>made operational.</em></h1></div><p>Historical maintenance records grouped into evidence-backed episodes. Every recommendation remains traceable to source work orders.</p></section>
    <MetricStrip metrics={data.metrics} />
    <OperationalPosture metrics={data.metrics} />
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
