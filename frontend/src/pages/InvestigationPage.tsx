import { Link, useParams } from "react-router-dom";

import { useApi } from "../api";
import { ConfidenceBadge, EvidenceIds, KeyValue, RiskMark, SectionHeading } from "../components/DataDisplay";
import { StatePanel } from "../components/StatePanel";
import { label, percent, shortDate } from "../format";
import type { IncidentDetail, IncidentSummary, WorkOrderEvidence } from "../types";

function ConfidencePanel({ detail }: { detail: IncidentDetail }) {
  const entries = Object.entries(detail.insight.confidence_components).filter((entry): entry is [string, number] => typeof entry[1] === "number" && entry[0] !== "score");
  return <section className="confidence-panel"><div className="confidence-head"><span>AUDITABLE CONFIDENCE</span><strong>{percent(detail.insight.confidence)}</strong></div>{entries.map(([name, value]) => <div className="confidence-row" key={name}><span>{label(name)}</span><i><b style={{ width: `${value * 100}%` }} /></i><code>{value.toFixed(2)}</code></div>)}</section>;
}

function ReasoningLanes({ detail }: { detail: IncidentDetail }) {
  const insight = detail.insight;
  const rejected = insight.review_decision === "REJECTED";
  return <section className="reasoning-lanes">
    <article className="lane evidence-lane"><header><span>01</span><div><strong>OBSERVED</strong><small>Direct record evidence</small></div></header>{insight.observations.map((observation) => <p key={observation}>{observation}</p>)}<EvidenceIds identifiers={insight.supporting_work_orders} /></article>
    <article className="lane inference-lane"><header><span>02</span><div><strong>INTERPRETED</strong><small>Rule-based synthesis</small></div></header><p>{insight.interpretation}</p><div className="cause-box"><span>{insight.possible_cause.support_level} CAUSE</span><strong>{insight.possible_cause.statement}</strong></div></article>
    <article className="lane action-lane"><header><span>03</span><div><strong>{rejected ? "REJECTED" : "RECOMMENDED"}</strong><small>{rejected ? "Do not action" : "Requires authorization"}</small></div></header><p>{rejected ? "A human reviewer rejected this generated finding. Retain it for audit only." : insight.recommended_action}</p>{!rejected && <Link to="/reviews" className="action-link">Open human review <span>-&gt;</span></Link>}</article>
  </section>;
}

function EvidenceCard({ order }: { order: WorkOrderEvidence }) {
  const meaningful = order.comments.filter((comment) => comment.is_meaningful);
  return <article className="evidence-card"><div className="evidence-date"><time>{shortDate(order.date)}</time><code>{order.work_order_id}</code></div><div className="evidence-body"><div className="evidence-meta"><span>{label(order.issue_family)}</span><span>{order.priority} priority</span><span>{order.status}</span></div>{meaningful.map((comment, index) => <blockquote key={`${order.work_order_id}-${index}`}><p>{comment.redacted_text}</p><small>{comment.source_type} note {comment.was_redacted && "/ PII redacted before display and AI processing"}</small></blockquote>)}{order.match_explanation.reasons && <div className="match-reasons">Grouped because: {order.match_explanation.reasons.join(" / ")}</div>}</div></article>;
}

function Investigation({ detail }: { detail: IncidentDetail }) {
  const incident = detail.incident;
  const evidenceIds = new Set(detail.work_orders.map((order) => order.work_order_id));
  const citations = [...detail.insight.supporting_work_orders, ...detail.insight.contradicting_work_orders];
  const grounded = citations.every((identifier) => evidenceIds.has(identifier));
  return <div className="page-stack reveal">{detail.insight.review_decision === "REJECTED" && <section className="rejection-banner"><strong>HUMAN REVIEW: REJECTED</strong><span>This finding is retained for audit and must not drive maintenance action.</span></section>}<section className="investigation-head"><div><span className="eyebrow">CASE FILE / {incident.incident_id}</span><h1>{detail.insight.title}</h1><p>{detail.insight.summary}</p></div><RiskMark score={incident.risk_score} /></section><section className="case-facts"><KeyValue item={{ name: "department", value: incident.department }} /><KeyValue item={{ name: "evidence window", value: `${shortDate(incident.first_seen)} - ${shortDate(incident.last_seen)}` }} /><KeyValue item={{ name: "resolution", value: label(incident.resolution_status) }} /><div className="key-value"><span>Confidence</span><ConfidenceBadge value={incident.confidence} /></div></section><ReasoningLanes detail={detail} /><div className="investigation-grid"><section className="panel evidence-panel"><SectionHeading data={{ index: "E", title: "Evidence timeline", note: "Descriptions omitted; redacted technician comments retained" }} />{detail.work_orders.map((order) => <EvidenceCard order={order} key={order.work_order_id} />)}</section><aside><ConfidencePanel detail={detail} /><section className={`grounding-note ${grounded ? "" : "failed"}`}><span>GROUNDING GATE</span><strong>{grounded ? "PASS" : "FAIL"}</strong><p>{grounded ? "All displayed citations occur inside this retrieved incident evidence set." : "A citation is outside the retrieved evidence set. Do not use this finding."}</p></section></aside></div></div>;
}

export function InvestigationPage() {
  const { incidentId } = useParams();
  const list = useApi<IncidentSummary[]>(incidentId ? null : "/incidents?recurring_only=true");
  const selectedId = incidentId ?? list.data?.[0]?.incident_id ?? null;
  const detail = useApi<IncidentDetail>(selectedId ? `/investigations/${selectedId}` : null);
  if (list.loading || detail.loading) return <StatePanel state="loading" />;
  if (list.error || detail.error) return <StatePanel state="error" message={list.error ?? detail.error ?? "Investigation unavailable"} retry={list.error ? list.reload : detail.reload} />;
  if (!detail.data) return <StatePanel state="empty" message="No recurring incident is available for investigation." />;
  return <Investigation detail={detail.data} />;
}
