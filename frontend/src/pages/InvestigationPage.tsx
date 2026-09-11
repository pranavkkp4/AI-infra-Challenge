import { Link, useParams } from "react-router-dom";

import { useApi } from "../api";
import { ConfidenceBadge, EvidenceIds, InlineEmpty, KeyValue, RiskMark, SectionHeading } from "../components/DataDisplay";
import { StatePanel } from "../components/StatePanel";
import { label, percent, shortDate } from "../format";
import type { IncidentDetail, IncidentPage, WorkOrderEvidence } from "../types";

function ConfidencePanel({ detail }: { detail: IncidentDetail }) {
  const entries = Object.entries(detail.insight.confidence_components).filter((entry): entry is [string, number] => typeof entry[1] === "number" && entry[0] !== "score");
  const calibrationApplied = detail.insight.confidence_components.calibration?.applied ?? false;
  const calibrationText = calibrationApplied
    ? "A provisional calibration curve is applied for review prioritization; it is not a failure probability."
    : "No calibration artifact is applied; this score ranks review priority only.";
  return <section className="confidence-panel"><div className="confidence-head"><span>{calibrationApplied ? "CALIBRATED SCORE" : "AUDITABLE SCORE"} / {detail.insight.confidence_level}</span><strong>{percent(detail.insight.confidence)}</strong></div><p className="confidence-policy">{detail.insight.requires_human_review ? "Review gate: human authorization required" : "Review gate: no human authorization required"}</p>{entries.map(([name, value]) => <div className={`confidence-row ${name === "conflict_penalty" ? "penalty" : ""}`} key={name}><span>{label(name)}</span><i><b style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} /></i><code>{value.toFixed(2)}</code></div>)}<p className="confidence-footnote">{calibrationText}</p></section>;
}

function ReasoningLanes({ detail }: { detail: IncidentDetail }) {
  const insight = detail.insight;
  const rejected = insight.review_decision === "REJECTED";
  return <section className="reasoning-lanes">
    <article className="lane evidence-lane"><header><span>01</span><div><strong>EVIDENCE</strong><small>Observed record facts</small></div></header>{insight.observations.length ? insight.observations.map((observation) => <p key={observation}>{observation}</p>) : <p className="muted-copy">No observation text returned.</p>}<EvidenceIds identifiers={insight.supporting_work_orders} />{insight.contradicting_work_orders.length > 0 && <div className="contradiction-note">Contradicting records<EvidenceIds identifiers={insight.contradicting_work_orders} /></div>}</article>
    <article className="lane inference-lane"><header><span>02</span><div><strong>INFERENCE</strong><small>Calibrated rule synthesis</small></div></header><p>{insight.interpretation}</p><div className="cause-box"><span>{insight.possible_cause.support_level} CAUSE</span><strong>{insight.possible_cause.statement}</strong></div></article>
    <article className="lane action-lane"><header><span>03</span><div><strong>{rejected ? "ACTION BLOCKED" : "ACTION"}</strong><small>{rejected ? "Rejected by human review" : "Requires authorization"}</small></div></header><p>{rejected ? "A human reviewer rejected this generated finding. Retain it for audit only." : insight.recommended_action}</p>{!rejected && (detail.incident.requires_human_review || insight.review_decision) && <Link to={`/reviews?decision=ALL&insight=${insight.insight_id}`} className="action-link">Open human review <span>-&gt;</span></Link>}</article>
  </section>;
}

function EvidenceCard({ order }: { order: WorkOrderEvidence }) {
  const meaningful = order.comments.filter((comment) => comment.is_meaningful);
  return <article className="evidence-card"><div className="evidence-date"><time>{shortDate(order.date)}</time><code>{order.work_order_id}</code></div><div className="evidence-body"><div className="evidence-meta"><span>{label(order.issue_family)}</span><span>{order.priority} priority</span><span>{order.status}</span>{order.site && <span>{order.site}</span>}</div>{meaningful.length ? meaningful.map((comment, index) => <blockquote key={`${order.work_order_id}-${index}`}><p>{comment.redacted_text}</p><small>{comment.source_type} note {comment.was_redacted && "/ PII redacted before display and AI processing"}</small></blockquote>) : <p className="muted-copy">No meaningful redacted comment was retained for display.</p>}{order.match_explanation.reasons && <div className="match-reasons">Grouped because: {order.match_explanation.reasons.join(" / ")}</div>}</div></article>;
}

function Investigation({ detail }: { detail: IncidentDetail }) {
  const incident = detail.incident;
  const evidenceIds = new Set(detail.work_orders.map((order) => order.work_order_id));
  const citations = [...detail.insight.supporting_work_orders, ...detail.insight.contradicting_work_orders];
  const grounded = citations.every((identifier) => evidenceIds.has(identifier));
   const scoreLabel = detail.insight.confidence_components.calibration?.applied ? "Calibrated confidence" : "Evidence confidence";
   return <div className="page-stack reveal">{detail.insight.review_decision === "REJECTED" && <section className="rejection-banner"><strong>HUMAN REVIEW: REJECTED</strong><span>This finding is retained for audit and must not drive maintenance action.</span></section>}<section className="investigation-head"><div><span className="eyebrow">CASE FILE / {incident.incident_id}</span><h1>{detail.insight.title}</h1><p>{detail.insight.summary}</p></div><RiskMark score={incident.risk_score} /></section><section className="case-facts"><KeyValue item={{ name: "department", value: incident.department }} /><KeyValue item={{ name: "evidence window", value: `${shortDate(incident.first_seen)} - ${shortDate(incident.last_seen)}` }} /><KeyValue item={{ name: "resolution", value: label(incident.resolution_status) }} /><div className="key-value"><span>{scoreLabel}</span><ConfidenceBadge value={incident.confidence} level={incident.confidence_level} /></div></section><section className="provenance-bar"><span>PROVENANCE</span><strong>{detail.insight.generated_by}</strong><small>{detail.insight.human_override ? "Human override active" : "Deterministic output; no human override"}</small></section><ReasoningLanes detail={detail} /><div className="investigation-grid"><section className="panel evidence-panel"><SectionHeading data={{ index: "E", title: "Evidence timeline", note: "Redacted technician comments retained; descriptions omitted" }} />{detail.work_orders.length ? detail.work_orders.map((order) => <EvidenceCard order={order} key={order.work_order_id} />) : <InlineEmpty message="No work-order evidence was returned for this incident." />}</section><aside><ConfidencePanel detail={detail} /><section className={`grounding-note ${grounded ? "" : "failed"}`}><span>GROUNDING GATE</span><strong>{grounded ? "PASS" : "FAIL"}</strong><p>{grounded ? "All displayed citations occur inside this retrieved incident evidence set." : "A citation is outside the retrieved evidence set. Do not use this finding."}</p></section></aside></div></div>;
}

export function InvestigationPage() {
  const { incidentId } = useParams();
  const list = useApi<IncidentPage>(incidentId ? null : "/incidents?recurring_only=true&limit=1");
  const selectedId = incidentId ?? list.data?.items[0]?.incident_id ?? null;
  const detail = useApi<IncidentDetail>(selectedId ? `/investigations/${selectedId}` : null);
  if (list.loading || detail.loading) return <StatePanel state="loading" />;
  if (list.error || detail.error) return <StatePanel state="error" message={list.error ?? detail.error ?? "Investigation unavailable"} retry={list.error ? list.reload : detail.reload} />;
  if (!detail.data) return <StatePanel state="empty" message="No recurring incident is available for investigation." />;
  return <Investigation detail={detail.data} />;
}
