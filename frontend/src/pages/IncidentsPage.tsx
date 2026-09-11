import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useApi } from "../api";
import { ConfidenceBadge, RiskMark } from "../components/DataDisplay";
import { Pagination } from "../components/Pagination";
import { StatePanel } from "../components/StatePanel";
import { label, shortDate } from "../format";
import type { IncidentPage, IncidentSummary } from "../types";

interface Filters {
  issue: string;
  department: string;
  confidence: string;
  recurring: boolean;
}

const PAGE_SIZE = 100;

function incidentPath(filters: Filters, offset: number): string {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  if (filters.issue) params.set("issue_family", filters.issue);
  if (filters.department) params.set("department", filters.department);
  if (filters.confidence) params.set("confidence", filters.confidence);
  if (filters.recurring) params.set("recurring_only", "true");
  return `/incidents?${params}`;
}

function FilterBar({ data }: { data: { facets: IncidentPage["facets"]; filters: Filters; setFilters: (value: Filters) => void } }) {
  const update = (key: keyof Filters, value: string | boolean) => data.setFilters({ ...data.filters, [key]: value });
  return <div className="filter-bar">
    <label>Issue family<select aria-label="Filter by issue family" value={data.filters.issue} onChange={(event) => update("issue", event.target.value)}><option value="">All families</option>{data.facets.issue_families.map((item) => <option value={item} key={item}>{label(item)}</option>)}</select></label>
    <label>Department<select aria-label="Filter by department" value={data.filters.department} onChange={(event) => update("department", event.target.value)}><option value="">All departments</option>{data.facets.departments.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
    <label>Confidence<select aria-label="Filter by confidence" value={data.filters.confidence} onChange={(event) => update("confidence", event.target.value)}><option value="">All levels</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select></label>
    <label className="check-filter"><input type="checkbox" checked={data.filters.recurring} onChange={(event) => update("recurring", event.target.checked)} /><span>Recurring only</span></label>
  </div>;
}

function IncidentTable({ rows }: { rows: IncidentSummary[] }) {
  const navigate = useNavigate();
  if (!rows.length) return <StatePanel state="empty" message="No incidents satisfy the active filter set." />;
  return <div className="data-table-wrap" tabIndex={0} role="region" aria-label="Incident register, horizontally scrollable"><table className="data-table"><caption className="sr-only">Grouped maintenance incident episodes</caption><thead><tr><th>Risk</th><th>Incident / Asset</th><th>Issue</th><th>Evidence window</th><th>WO count</th><th>Confidence</th><th>Status</th></tr></thead><tbody>{rows.map((row) => (
    <tr aria-label={`Open incident ${row.incident_id}`} key={row.incident_id} onClick={() => navigate(`/investigations/${row.incident_id}`)} role="link" tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); navigate(`/investigations/${row.incident_id}`); } }}>
      <td><RiskMark score={row.risk_score} /></td><td><strong>{row.incident_id}</strong><small>{row.asset_key}</small></td><td><span className="issue-tag">{label(row.issue_family)}</span><small>{row.department}</small></td><td>{shortDate(row.first_seen)}<small>to {shortDate(row.last_seen)}</small></td><td><strong>{row.work_order_count}</strong>{row.recurring && <small className="repeat-flag">REPEAT</small>}</td><td><ConfidenceBadge value={row.confidence} level={row.confidence_level} /></td><td><span className={`resolution ${row.resolution_status.toLowerCase()}`}>{label(row.resolution_status)}</span></td>
    </tr>
  ))}</tbody></table></div>;
}

export function IncidentsPage() {
  const [params, setParams] = useSearchParams();
  const requestedOffset = Number(params.get("offset") ?? 0);
  const offset = Number.isInteger(requestedOffset) && requestedOffset >= 0 ? requestedOffset : 0;
  const filters: Filters = {
    issue: params.get("issue") ?? "",
    department: params.get("department") ?? "",
    confidence: params.get("confidence") ?? "",
    recurring: params.get("recurring") === "true",
  };
  const result = useApi<IncidentPage>(incidentPath(filters, offset));
  useEffect(() => {
    if (!result.data || offset < result.data.total || offset === 0) return;
    const lastPage = Math.max(0, Math.floor((result.data.total - 1) / PAGE_SIZE) * PAGE_SIZE);
    setParams(filterParams(filters, lastPage), { replace: true });
  }, [filters, offset, result.data, setParams]);
  const updateFilters = (value: Filters) => setParams(filterParams(value, 0));
  const setOffset = (value: number) => setParams(filterParams(filters, value));
  if (result.loading && !result.data) return <StatePanel state="loading" />;
  if (result.error) return <StatePanel state="error" message={result.error} retry={result.reload} />;
  const page = result.data;
  const rows = page?.items ?? [];
  return <div className="page-stack reveal"><section className="page-title"><div><span className="eyebrow">EPISODE REGISTER</span><h1>Incident Explorer</h1></div><p><strong>{page?.total ?? 0}</strong> grouped maintenance episodes match this view</p></section>{page && <FilterBar data={{ facets: page.facets, filters, setFilters: updateFilters }} />}<IncidentTable rows={rows} />{page && <Pagination data={{ ...page, setOffset }} />}</div>;
}

function filterParams(filters: Filters, offset: number): URLSearchParams {
  const params = new URLSearchParams({ offset: String(offset) });
  if (filters.issue) params.set("issue", filters.issue);
  if (filters.department) params.set("department", filters.department);
  if (filters.confidence) params.set("confidence", filters.confidence);
  if (filters.recurring) params.set("recurring", "true");
  return params;
}
