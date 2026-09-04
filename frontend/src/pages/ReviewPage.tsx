import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiPatch, useApi } from "../api";
import { ConfidenceBadge, EvidenceIds, SectionHeading } from "../components/DataDisplay";
import { StatePanel } from "../components/StatePanel";
import { label } from "../format";
import type { ReviewDecision, ReviewItem } from "../types";

function ReviewList({ data }: { data: { reviews: ReviewItem[]; activeId: string | null; select: (id: string) => void } }) {
  return <div className="review-list">{data.reviews.map((review) => (
    <button className={data.activeId === review.review_id ? "active" : ""} key={review.review_id} onClick={() => data.select(review.review_id)}>
      <span className="review-state">{review.decision.slice(0, 1)}</span><div><strong>{label(review.incident.issue_family)}</strong><small>{review.incident.asset_key}</small><code>{review.incident.incident_id}</code></div><ConfidenceBadge value={review.incident.confidence} />
    </button>
  ))}</div>;
}

interface ReviewActionData {
  item: ReviewItem;
  note: string;
  setNote: (note: string) => void;
  submit: (decision: ReviewDecision) => Promise<void>;
  submitting: boolean;
  message: string | null;
}

function ReviewAction({ data }: { data: ReviewActionData }) {
  const insight = data.item.insight;
  const rejected = data.item.decision === "REJECTED";
  return <div className="review-action reveal">{rejected && <section className="rejection-banner"><strong>HUMAN REVIEW: REJECTED</strong><span>This finding is retained for audit and excluded from operational metrics.</span></section>}<div className="review-action-head"><div><span>REVIEW ITEM / {data.item.review_id}</span><h2>{insight.title}</h2></div><ConfidenceBadge value={insight.confidence} /></div><section className="review-comparison"><article><span>OBSERVATION</span>{insight.observations.map((item) => <p key={item}>{item}</p>)}</article><article><span>MODEL INTERPRETATION</span><p>{insight.interpretation}</p></article><article><span>{rejected ? "REJECTED ACTION / AUDIT ONLY" : "PROPOSED ACTION"}</span><p>{insight.recommended_action}</p></article></section><section className="citation-check"><strong>Citation set</strong><EvidenceIds identifiers={insight.supporting_work_orders} /><Link to={`/investigations/${insight.incident_id}`}>Inspect source timeline -&gt;</Link></section><label className="review-note">Reviewer note<textarea value={data.note} maxLength={2000} onChange={(event) => data.setNote(event.target.value)} placeholder="Record evidence checked, corrections, or rejection rationale..." /></label>{data.message && <p className="form-message">{data.message}</p>}<div className="review-controls"><button disabled={data.submitting} className="reject-button" onClick={() => data.submit("REJECTED")}>Reject finding</button><button disabled={data.submitting} className="hold-button" onClick={() => data.submit("PENDING")}>Hold for evidence</button><button disabled={data.submitting} className="confirm-button" onClick={() => data.submit("CONFIRMED")}>Confirm finding</button></div></div>;
}

function ActiveReview({ data }: { data: { item: ReviewItem; reload: () => void } }) {
  const [note, setNote] = useState(data.item.reviewer_note ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => setNote(data.item.reviewer_note ?? ""), [data.item]);
  const submit = async (decision: ReviewDecision) => {
    setSubmitting(true); setMessage(null);
    try {
      await apiPatch(`/reviews/${data.item.insight.insight_id}`, { decision, reviewer_note: note || null });
      setMessage(`Decision saved as ${decision}.`); data.reload();
    } catch (error: unknown) {
      setMessage(`Update failed: ${String(error)}`);
    } finally {
      setSubmitting(false);
    }
  };
  return <ReviewAction data={{ item: data.item, note, setNote, submit, submitting, message }} />;
}

export function ReviewPage() {
  const result = useApi<ReviewItem[]>("/reviews");
  const health = useApi<{ review_threshold: number }>("/health");
  const [activeId, setActiveId] = useState<string | null>(null);
  useEffect(() => { if (!activeId && result.data?.[0]) setActiveId(result.data[0].review_id); }, [activeId, result.data]);
  if (result.loading && !result.data) return <StatePanel state="loading" />;
  if (result.error) return <StatePanel state="error" message={result.error} retry={result.reload} />;
  const pending = result.data?.filter((review) => review.decision === "PENDING") ?? [];
  const reviews = result.data ?? [];
  const active = reviews.find((review) => review.review_id === activeId) ?? reviews[0];
  if (!active) return <StatePanel state="empty" message="No findings currently require human review." />;
  const threshold = health.data ? `${Math.round(health.data.review_threshold * 100)}%` : "configured";
  return <div className="page-stack reveal"><section className="page-title"><div><span className="eyebrow">HUMAN-IN-THE-LOOP</span><h1>Review Queue</h1></div><p><strong>{pending.length}</strong> findings below the {threshold} policy threshold</p></section><div className="review-layout"><aside className="review-register"><div className="register-head"><strong>LOW CONFIDENCE FIRST</strong><span>{reviews.length}</span></div><ReviewList data={{ reviews, activeId: active.review_id, select: setActiveId }} /></aside><section className="panel review-detail"><ActiveReview data={{ item: active, reload: result.reload }} /></section></div></div>;
}
