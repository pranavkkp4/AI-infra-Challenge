import { label, percent, riskBand } from "../format";

export function ConfidenceBadge({ value }: { value: number }) {
  const level = value >= 0.82 ? "HIGH" : value >= 0.65 ? "MEDIUM" : "LOW";
  return <span className={`confidence-badge ${level.toLowerCase()}`}>{level} / {percent(value)}</span>;
}

export function RiskMark({ score }: { score: number }) {
  return <span className={`risk-mark ${riskBand(score)}`}><b>{score}</b><small>RISK</small></span>;
}

export function EvidenceIds({ identifiers }: { identifiers: string[] }) {
  return <div className="evidence-ids">{identifiers.map((id) => <code key={id}>{id}</code>)}</div>;
}

export function SectionHeading({ data }: { data: { index: string; title: string; note?: string } }) {
  return (
    <div className="section-heading">
      <span>{data.index}</span>
      <div><h2>{data.title}</h2>{data.note && <p>{data.note}</p>}</div>
    </div>
  );
}

export function KeyValue({ item }: { item: { name: string; value: string } }) {
  return <div className="key-value"><span>{label(item.name)}</span><strong>{item.value}</strong></div>;
}
