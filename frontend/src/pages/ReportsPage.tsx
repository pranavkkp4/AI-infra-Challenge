import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { downloadReport, useApi } from "../api";
import { EvidenceIds, InlineEmpty, SectionHeading } from "../components/DataDisplay";
import { StatePanel } from "../components/StatePanel";
import { days, label, percent } from "../format";
import type { DashboardData, SearchResult, TaxonomyPhrase } from "../types";

function SearchResults({ result }: { result: SearchResult }) {
  const filters = Object.entries(result.interpreted_filters).filter(
    ([, value]) => value !== null,
  );
  return (
    <section className="search-results reveal">
      <div className="query-interpretation">
        <span>QUERY INTERPRETATION</span>
        <strong>{result.summary}</strong>
        <div>
          {filters.map(([key, value]) => <code key={key}>{label(key)}: {value}</code>)}
        </div>
      </div>
      <div className="result-columns">
        <article>
          <SectionHeading data={{ index: "A", title: "Matched assets" }} />
          {result.assets.length ? result.assets.map((asset) => (
            <Link to={`/assets?asset=${encodeURIComponent(asset.asset_key)}&class=${asset.asset_class}`} key={asset.asset_key}>
              <strong>{asset.asset_key}</strong>
              <span>{asset.matching_incidents} incidents / risk {asset.risk_score}</span>
            </Link>
          )) : <InlineEmpty message="No assets matched this query." />}
        </article>
        <article>
          <SectionHeading data={{ index: "I", title: "Matched incidents" }} />
          {result.incidents.length ? result.incidents.map((incident) => (
            <Link to={`/investigations/${incident.incident_id}`} key={incident.incident_id}>
              <strong>{incident.incident_id}</strong>
              <span>{label(incident.issue_family)} / {percent(incident.confidence)} confidence</span>
              <EvidenceIds identifiers={incident.supporting_work_orders} />
            </Link>
          )) : <InlineEmpty message="No grouped incidents matched this query." />}
        </article>
        <article>
          <SectionHeading data={{ index: "W", title: "Nearest work orders" }} />
          {result.work_orders.length ? result.work_orders.slice(0, 8).map((order) => (
            <div className="search-order" key={order.work_order_id}>
              <strong>{order.work_order_id}</strong>
              <span>{order.evidence_excerpt || "No redacted note excerpt available."}</span>
              <code>{order.semantic_score.toFixed(3)}</code>
            </div>
          )) : <InlineEmpty message="No nearby work-order evidence was found." />}
        </article>
      </div>
    </section>
  );
}

function Taxonomy({ phrases }: { phrases: TaxonomyPhrase[] }) {
  const max = Math.max(...phrases.map((item) => item.score), 1);
  if (!phrases.length) return <InlineEmpty message="No meaningful redacted phrases are available." />;
  return (
    <div className="taxonomy-list">
      {phrases.slice(0, 12).map((item, index) => (
        <div key={item.phrase}>
          <span>{String(index + 1).padStart(2, "0")}</span>
          <strong>{item.phrase}</strong>
          <i><b style={{ width: `${item.score / max * 100}%` }} /></i>
          <code>{item.score.toFixed(3)}</code>
        </div>
      ))}
    </div>
  );
}

function ReportReadiness({ dashboard }: { dashboard: DashboardData }) {
  const calibration = dashboard.calibration ?? { applied: false };
  const intervalSummary = `${dashboard.metrics.pm_interval_recommendations ?? 0} proposed / ${dashboard.metrics.pm_interval_abstentions ?? 0} held`;
  const checks = [
    { name: "Canonical work orders", value: String(dashboard.metrics.total_work_orders), status: dashboard.metrics.total_work_orders ? "READY" : "HOLD", tone: dashboard.metrics.total_work_orders ? "ready" : "hold" },
    { name: "Evidence-backed patterns", value: String(dashboard.patterns.length), status: dashboard.patterns.length ? "READY" : "HOLD", tone: dashboard.patterns.length ? "ready" : "hold" },
    { name: "Human review backlog", value: String(dashboard.metrics.human_review_count), status: dashboard.metrics.human_review_count ? "REVIEW" : "CLEAR", tone: dashboard.metrics.human_review_count ? "review" : "ready" },
    { name: "High-risk equipment", value: String(dashboard.metrics.high_risk_assets), status: dashboard.metrics.high_risk_assets ? "WATCH" : "CLEAR", tone: dashboard.metrics.high_risk_assets ? "watch" : "ready" },
    { name: "Observed repeat interval", value: days(dashboard.metrics.mean_time_between_repeats), status: "CONTEXT", tone: "context" },
    { name: "PM interval analysis", value: intervalSummary, status: "CONTEXT", tone: "context" },
    { name: "Confidence calibration", value: calibration.applied ? (calibration.synthetic ? "PROVISIONAL DEMO" : "APPLIED") : "NOT CONFIGURED", status: calibration.applied ? "READY" : "HOLD", tone: calibration.applied ? "ready" : "hold" },
  ];
  const blockers = checks.filter((check) => check.status === "HOLD").length;
  return (
    <>
      <div className={`readiness-summary ${blockers ? "needs-review" : "ready"}`}>
        <strong>{blockers ? "READY WITH GATES" : "READY FOR REVIEW"}</strong>
        <span>{blockers ? `${blockers} authorization gate${blockers === 1 ? "" : "s"} remain` : "Evidence package is internally complete"}</span>
      </div>
      <div className="readiness-list">
        {checks.map((check) => (
          <div key={check.name}>
            <span className={`check-mark ${check.tone}`}>{check.status}</span>
            <strong>{check.name}</strong>
            <code>{check.value}</code>
          </div>
        ))}
      </div>
    </>
  );
}

export function ReportsPage() {
  const dashboard = useApi<DashboardData>("/dashboard");
  const taxonomy = useApi<TaxonomyPhrase[]>("/taxonomy/phrases");
  const [input, setInput] = useState("recurring low pressure in 2023");
  const [query, setQuery] = useState<string | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"md" | "json" | null>(null);
  const search = useApi<SearchResult>(query ? `/search?q=${encodeURIComponent(query)}` : null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (input.trim().length < 2) {
      setQueryError("Enter at least 2 characters to search the bounded evidence set.");
      return;
    }
    setQueryError(null);
    setQuery(input.trim());
  };
  const download = async (format: "md" | "json") => {
    setDownloadError(null);
    setDownloading(format);
    try {
      await downloadReport(format);
    } catch (error: unknown) {
      setDownloadError(error instanceof Error ? error.message : "Report download failed.");
    } finally {
      setDownloading(null);
    }
  };
  const runExample = (value: string) => {
    setInput(value);
    setQueryError(null);
    setQuery(value);
  };

  if (dashboard.error || taxonomy.error) {
    return <StatePanel state="error" message={dashboard.error ?? taxonomy.error ?? "Report services unavailable"} retry={() => { dashboard.reload(); taxonomy.reload(); }} />;
  }
  if (dashboard.loading || taxonomy.loading) return <StatePanel state="loading" />;
  if (!dashboard.data || !taxonomy.data) return <StatePanel state="empty" message="The report package is not ready yet." />;

  return (
    <div className="page-stack reveal">
      <section className="page-title">
        <div>
          <span className="eyebrow">DISPATCH BRIEFING</span>
          <h1>Reports + Search</h1>
          {downloadError && <p className="form-message" role="alert">{downloadError}</p>}
        </div>
        <div className="report-actions">
          <button type="button" className="download-button" disabled={Boolean(downloading)} aria-busy={downloading === "md"} onClick={() => download("md")}>{downloading === "md" ? "Preparing report" : "Download report"} <span>MD</span></button>
          <button type="button" className="download-button" disabled={Boolean(downloading)} aria-busy={downloading === "json"} onClick={() => download("json")}>{downloading === "json" ? "Preparing report" : "Structured report"} <span>JSON</span></button>
        </div>
      </section>
      <section className="report-grid">
        <article className="panel report-card">
          <SectionHeading data={{ index: "R", title: "Report readiness", note: dashboard.data?.dataset_label ?? "Grounded analysis package" }} />
          <ReportReadiness dashboard={dashboard.data} />
      <p className="report-disclaimer">{dashboard.data.dataset_label} is labeled synthetic when applicable. Findings are decision support; preventive work requires departmental review and authorization. {calibrationNote(dashboard.data.calibration)}</p>
        </article>
        <article className="panel">
          <SectionHeading data={{ index: "T", title: "Emergent taxonomy", note: "Frequent 2-3 word phrases from redacted comments" }} />
          <Taxonomy phrases={taxonomy.data} />
        </article>
      </section>
      <section className="search-console">
        <span className="eyebrow">DARK-DATA NOTE RETRIEVAL</span>
        <h2>Ask the maintenance history.</h2>
        <form onSubmit={submit}>
          <span>?</span>
          <input aria-label="Search maintenance notes" aria-describedby="search-help" aria-invalid={Boolean(queryError)} minLength={2} maxLength={500} required value={input} onChange={(event) => { setInput(event.target.value); setQueryError(null); }} placeholder="Try: assets with more than 2 recurring water leaks in 2023" />
          <button type="submit">Run query</button>
        </form>
        <small id="search-help" className="search-help">Queries are interpreted against redacted notes and linked work orders only.{queryError && <span role="alert"> {queryError}</span>}</small>
        <div className="query-examples">
          <button type="button" onClick={() => runExample("recurring streetlights out")}>Recurring streetlights out</button>
          <button type="button" onClick={() => runExample("low pressure in 2023")}>Low pressure / 2023</button>
          <button type="button" onClick={() => runExample("pavement damage")}>Pavement damage</button>
        </div>
      </section>
      {search.loading && <StatePanel state="loading" message="Searching redacted work-order evidence." />}
      {search.error && <StatePanel state="error" message={search.error} retry={search.reload} />}
      {search.data && <SearchResults result={search.data} />}
    </div>
  );
}

function calibrationNote(calibration: DashboardData["calibration"]): string {
  if (!calibration) return "Confidence is not calibrated for this dataset.";
  if (!calibration.applied) return "Confidence is not calibrated for this dataset.";
  if (calibration.synthetic) return "The active curve is provisional and applies only to the bundled demo fixture.";
  return `Calibration artifact ${calibration.artifact_id ?? "configured"} is active.`;
}
