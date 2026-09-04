import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { downloadReport, useApi } from "../api";
import { EvidenceIds, SectionHeading } from "../components/DataDisplay";
import { StatePanel } from "../components/StatePanel";
import { label } from "../format";
import type { DashboardData, SearchResult, TaxonomyPhrase } from "../types";

function SearchResults({ result }: { result: SearchResult }) {
  return <section className="search-results reveal"><div className="query-interpretation"><span>QUERY INTERPRETATION</span><strong>{result.summary}</strong><div>{Object.entries(result.interpreted_filters).filter(([, value]) => value !== null).map(([key, value]) => <code key={key}>{label(key)}: {value}</code>)}</div></div><div className="result-columns"><article><SectionHeading data={{ index: "A", title: "Matched assets" }} />{result.assets.map((asset) => <Link to={`/assets?asset=${encodeURIComponent(asset.asset_key)}`} key={asset.asset_key}><strong>{asset.asset_key}</strong><span>{asset.matching_incidents} incidents / risk {asset.risk_score}</span></Link>)}</article><article><SectionHeading data={{ index: "I", title: "Matched incidents" }} />{result.incidents.map((incident) => <Link to={`/investigations/${incident.incident_id}`} key={incident.incident_id}><strong>{incident.incident_id}</strong><span>{label(incident.issue_family)} / {Math.round(incident.confidence * 100)}%</span><EvidenceIds identifiers={incident.supporting_work_orders} /></Link>)}</article><article><SectionHeading data={{ index: "W", title: "Nearest work orders" }} />{result.work_orders.slice(0, 8).map((order) => <div className="search-order" key={order.work_order_id}><strong>{order.work_order_id}</strong><span>{order.description}</span><code>{order.semantic_score.toFixed(3)}</code></div>)}</article></div></section>;
}

function Taxonomy({ phrases }: { phrases: TaxonomyPhrase[] }) {
  const max = Math.max(...phrases.map((item) => item.score), 1);
  return <div className="taxonomy-list">{phrases.slice(0, 12).map((item, index) => <div key={item.phrase}><span>{String(index + 1).padStart(2, "0")}</span><strong>{item.phrase}</strong><i><b style={{ width: `${item.score / max * 100}%` }} /></i><code>{item.score.toFixed(3)}</code></div>)}</div>;
}

function ReportReadiness({ dashboard }: { dashboard: DashboardData }) {
  const checks = [
    ["Canonical work orders", dashboard.metrics.total_work_orders],
    ["Evidence-backed patterns", dashboard.patterns.length],
    ["Human review backlog", dashboard.metrics.human_review_count],
    ["High-risk assets", dashboard.metrics.high_risk_assets],
  ];
  return <div className="readiness-list">{checks.map(([name, value]) => <div key={name}><span className="check-mark">OK</span><strong>{name}</strong><code>{value}</code></div>)}</div>;
}

export function ReportsPage() {
  const dashboard = useApi<DashboardData>("/dashboard");
  const taxonomy = useApi<TaxonomyPhrase[]>("/taxonomy/phrases");
  const [input, setInput] = useState("recurring low pressure in 2023");
  const [query, setQuery] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const search = useApi<SearchResult>(query ? `/search?q=${encodeURIComponent(query)}` : null);
  const submit = (event: FormEvent) => { event.preventDefault(); if (input.trim().length >= 2) setQuery(input.trim()); };
  const download = async () => {
    setDownloadError(null);
    try {
      await downloadReport();
    } catch (error: unknown) {
      setDownloadError(String(error));
    }
  };
  if (dashboard.loading || taxonomy.loading) return <StatePanel state="loading" />;
  if (dashboard.error || taxonomy.error) return <StatePanel state="error" message={dashboard.error ?? taxonomy.error ?? "Report services unavailable"} retry={() => { if (dashboard.error) dashboard.reload(); if (taxonomy.error) taxonomy.reload(); }} />;
  return <div className="page-stack reveal"><section className="page-title"><div><span className="eyebrow">DISPATCH BRIEFING</span><h1>Reports + Search</h1>{downloadError && <p className="form-message">{downloadError}</p>}</div><button className="download-button" onClick={download}>Download PM report <span>MD</span></button></section><section className="report-grid"><article className="panel report-card"><SectionHeading data={{ index: "R", title: "Report readiness", note: dashboard.data?.dataset_label ?? "Grounded analysis package" }} />{dashboard.data && <ReportReadiness dashboard={dashboard.data} />}<p className="report-disclaimer">Generated findings are decision support. Preventive work requires departmental review and authorization.</p></article><article className="panel"><SectionHeading data={{ index: "T", title: "Emergent taxonomy", note: "Frequent 2-3 word phrases from redacted comments" }} />{taxonomy.data && <Taxonomy phrases={taxonomy.data} />}</article></section><section className="search-console"><span className="eyebrow">HYBRID RECORD RETRIEVAL</span><h2>Ask the maintenance history.</h2><form onSubmit={submit}><span>?</span><input aria-label="Search maintenance records" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Try: assets with more than 2 recurring leaks in 2023" /><button type="submit">Run query</button></form><div className="query-examples"><button onClick={() => { setInput("recurring sewer backups"); setQuery("recurring sewer backups"); }}>Recurring sewer backups</button><button onClick={() => { setInput("low pressure in 2023"); setQuery("low pressure in 2023"); }}>Low pressure / 2023</button><button onClick={() => { setInput("pavement damage"); setQuery("pavement damage"); }}>Pavement damage</button></div></section>{search.loading && <StatePanel state="loading" message="Parsing filters and ranking bounded semantic neighbors." />}{search.error && <StatePanel state="error" message={search.error} retry={search.reload} />}{search.data && <SearchResults result={search.data} />}</div>;
}
