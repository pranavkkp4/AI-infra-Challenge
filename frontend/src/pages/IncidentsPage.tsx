import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useApi } from "../api";
import { ConfidenceBadge, RiskMark } from "../components/DataDisplay";
import { StatePanel } from "../components/StatePanel";
import { label, shortDate } from "../format";
import type { IncidentSummary } from "../types";

interface Filters {
  issue: string;
  department: string;
  confidence: string;
  recurring: boolean;
}

const initialFilters: Filters = { issue: "", department: "", confidence: "", recurring: false };

function filterRows(rows: IncidentSummary[], filters: Filters): IncidentSummary[] {
  return rows.filter((row) =>
    (!filters.issue || row.issue_family === filters.issue)
    && (!filters.department || row.department === filters.department)
    && (!filters.confidence || row.confidence_level === filters.confidence)
    && (!filters.recurring || row.recurring));
}

function FilterBar({ data }: { data: { rows: IncidentSummary[]; filters: Filters; setFilters: (value: Filters) => void } }) {
  const issues = [...new Set(data.rows.map((row) => row.issue_family))];
  const departments = [...new Set(data.rows.map((row) => row.department))];
  const update = (key: keyof Filters, value: string | boolean) => data.setFilters({ ...data.filters, [key]: value });
  return <div className="filter-bar">
    <label>Issue family<select value={data.filters.issue} onChange={(event) => update("issue", event.target.value)}><option value="">All families</option>{issues.map((item) => <option value={item} key={item}>{label(item)}</option>)}</select></label>
    <label>Department<select value={data.filters.department} onChange={(event) => update("department", event.target.value)}><option value="">All departments</option>{departments.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
    <label>Confidence<select value={data.filters.confidence} onChange={(event) => update("confidence", event.target.value)}><option value="">All levels</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select></label>
    <label className="check-filter"><input type="checkbox" checked={data.filters.recurring} onChange={(event) => update("recurring", event.target.checked)} /><span>Recurring only</span></label>
  </div>;
}

function IncidentTable({ rows }: { rows: IncidentSummary[] }) {
  const navigate = useNavigate();
  if (!rows.length) return <StatePanel state="empty" message="No incidents satisfy the active filter set." />;
  return <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Risk</th><th>Incident / Asset</th><th>Issue</th><th>Evidence window</th><th>WO count</th><th>Confidence</th><th>Status</th></tr></thead><tbody>{rows.map((row) => (
    <tr key={row.incident_id} onClick={() => navigate(`/investigations/${row.incident_id}`)} tabIndex={0} onKeyDown={(event) => event.key === "Enter" && navigate(`/investigations/${row.incident_id}`)}>
      <td><RiskMark score={row.risk_score} /></td><td><strong>{row.incident_id}</strong><small>{row.asset_key}</small></td><td><span className="issue-tag">{label(row.issue_family)}</span><small>{row.department}</small></td><td>{shortDate(row.first_seen)}<small>to {shortDate(row.last_seen)}</small></td><td><strong>{row.work_order_count}</strong>{row.recurring && <small className="repeat-flag">REPEAT</small>}</td><td><ConfidenceBadge value={row.confidence} /></td><td><span className={`resolution ${row.resolution_status.toLowerCase()}`}>{label(row.resolution_status)}</span></td>
    </tr>
  ))}</tbody></table></div>;
}

export function IncidentsPage() {
  const result = useApi<IncidentSummary[]>("/incidents");
  const [filters, setFilters] = useState(initialFilters);
  if (result.loading) return <StatePanel state="loading" />;
  if (result.error) return <StatePanel state="error" message={result.error} retry={result.reload} />;
  const rows = result.data ? filterRows(result.data, filters) : [];
  return <div className="page-stack reveal"><section className="page-title"><div><span className="eyebrow">EPISODE REGISTER</span><h1>Incident Explorer</h1></div><p><strong>{rows.length}</strong> of {result.data?.length ?? 0} grouped maintenance episodes</p></section><FilterBar data={{ rows: result.data ?? [], filters, setFilters }} /><IncidentTable rows={rows} /></div>;
}
