import { label, percent, riskBand } from "../format";
import type { ConfidenceLevel } from "../types";

export function ConfidenceBadge({ value, level: providedLevel }: { value: number; level?: ConfidenceLevel }) {
  const level = providedLevel ?? (value >= 0.82 ? "HIGH" : value >= 0.65 ? "MEDIUM" : "LOW");
  return (
    <span
      className={`confidence-badge ${level.toLowerCase()}`}
      aria-label={`Confidence ${level.toLowerCase()}, ${percent(value)}`}
      title="Evidence-consistency score; calibration status is shown in the investigation provenance"
    >
      {level} / {percent(value)}
    </span>
  );
}

export function RiskMark({ score }: { score: number }) {
  return <span className={`risk-mark ${riskBand(score)}`}><b>{score}</b><small>RISK</small></span>;
}

export function EvidenceIds({ identifiers }: { identifiers: string[] }) {
  return (
    <div className="evidence-ids" aria-label="Supporting work orders">
      {identifiers.length ? identifiers.map((id) => <code key={id}>{id}</code>) : <span className="no-evidence">No supporting citations</span>}
    </div>
  );
}

export function SectionHeading({ data }: { data: { index: string; title: string; note?: string } }) {
  return (
    <div className="section-heading">
      <span>{data.index}</span>
      <div><h2>{data.title}</h2>{data.note && <p>{data.note}</p>}</div>
    </div>
  );
}

export function InlineEmpty({ message }: { message: string }) {
  return <p className="inline-empty" role="status">{message}</p>;
}

export function KeyValue({ item }: { item: { name: string; value: string } }) {
  return <div className="key-value"><span>{label(item.name)}</span><strong>{item.value}</strong></div>;
}
