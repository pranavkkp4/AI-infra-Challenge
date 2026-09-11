import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useApi } from "../api";
import { InlineEmpty, RiskMark, SectionHeading } from "../components/DataDisplay";
import { Pagination } from "../components/Pagination";
import { StatePanel } from "../components/StatePanel";
import { label, shortDate } from "../format";
import type { AssetDetail, AssetSummary, Page } from "../types";

const PAGE_SIZE = 100;

function AssetList({ data }: { data: { assets: AssetSummary[]; selected: string | null; select: (key: string) => void } }) {
  if (!data.assets.length) return <InlineEmpty message="No assets are available in this register." />;
  return <div className="asset-list">{data.assets.map((asset) => (
    <button type="button" aria-label={`Inspect asset ${asset.entity_uid}`} aria-pressed={data.selected === asset.asset_key} className={data.selected === asset.asset_key ? "active" : ""} key={asset.asset_key} onClick={() => data.select(asset.asset_key)}>
      <RiskMark score={asset.risk_score} /><span><strong>{asset.entity_uid}</strong><small>{label(asset.entity_type)} / {asset.department}</small></span><i>+</i>
    </button>
  ))}</div>;
}

function AssetTimeline({ timeline }: { timeline: AssetDetail["timeline"] }) {
  if (!timeline.length) return <InlineEmpty message="No maintenance chronology is available for this asset." />;
  return <div className="asset-timeline">{timeline.map((item) => (
    <article key={item.work_order_id} className={item.is_repeat ? "repeat" : ""}>
      <time>{shortDate(item.date)}</time><span className="timeline-pin" /><div><strong>{label(item.issue_family)}</strong><small>{item.category} / {item.status}</small></div><code>{item.work_order_id}</code>
    </article>
  ))}</div>;
}

function AssetProfile({ detail }: { detail: AssetDetail }) {
  const asset = detail.asset;
  return <div className="asset-profile reveal">
    <section className="asset-hero"><RiskMark score={asset.risk_score} /><div><span>{asset.asset_class} / {asset.entity_type}</span><h2>{asset.entity_uid}</h2><code>{asset.asset_key}</code></div></section>
    <div className="asset-stats"><div><span>Work orders</span><strong>{asset.total_work_orders}</strong></div><div><span>Recurring episodes</span><strong>{asset.recurring_issues}</strong></div><div><span>Last service</span><strong>{shortDate(asset.last_service_date)}</strong></div></div>
    <section className="reason-strip"><strong>Why this score</strong>{asset.risk_reasons.length ? asset.risk_reasons.map((reason) => <span key={reason}>{reason}</span>) : <span>No elevated risk factors were returned.</span>}</section>
    <SectionHeading data={{ index: "T", title: "Maintenance chronology", note: "Repeat episodes carry an orange rail" }} />
    <AssetTimeline timeline={detail.timeline} />
    <section className="asset-incidents"><SectionHeading data={{ index: "I", title: "Linked intelligence" }} />{detail.incidents.length ? detail.incidents.map((incident) => <Link to={`/investigations/${incident.incident_id}`} key={incident.incident_id}><span>{label(incident.issue_family)}</span><strong>{incident.incident_id}</strong><small>{incident.work_order_count} source orders / {Math.round(incident.confidence * 100)}% confidence</small></Link>) : <InlineEmpty message="No active incident intelligence is linked to this asset." />}</section>
  </div>;
}

function AssetSelection({ assetKey }: { assetKey: string | null }) {
  const detail = useApi<AssetDetail>(assetKey ? `/assets/${encodeURIComponent(assetKey)}` : null);
  if (detail.loading) return <StatePanel state="loading" />;
  if (detail.error) return <StatePanel state="error" message={detail.error} retry={detail.reload} />;
  if (!detail.data) return <StatePanel state="empty" message="Select an asset from the register to inspect its maintenance chronology." />;
  return <AssetProfile detail={detail.data} />;
}

export function AssetsPage() {
  const [params, setParams] = useSearchParams();
  const assetClass = params.get("class") === "location" ? "location" : "equipment";
  const requestedOffset = Number(params.get("offset") ?? 0);
  const offset = Number.isInteger(requestedOffset) && requestedOffset >= 0 ? requestedOffset : 0;
  const result = useApi<Page<AssetSummary>>(`/assets?asset_class=${assetClass}&limit=${PAGE_SIZE}&offset=${offset}`);
  useEffect(() => {
    if (!result.data || offset < result.data.total || offset === 0) return;
    const lastPage = Math.max(0, Math.floor((result.data.total - 1) / PAGE_SIZE) * PAGE_SIZE);
    setParams({ class: assetClass, offset: String(lastPage) }, { replace: true });
  }, [assetClass, offset, result.data, setParams]);
  const selected = params.get("asset") ?? result.data?.items[0]?.asset_key ?? null;
  const select = (assetKey: string) => setParams({ asset: assetKey, class: assetClass, offset: String(offset) });
  const chooseClass = (value: "equipment" | "location") => {
    setParams({ class: value, offset: "0" });
  };
  const setOffset = (value: number) => setParams({ class: assetClass, offset: String(value) });
  if (result.loading && !result.data) return <StatePanel state="loading" />;
  if (result.error) return <StatePanel state="error" message={result.error} retry={result.reload} />;
  const page = result.data;
  return <div className="page-stack reveal"><section className="page-title"><div><span className="eyebrow">RISK REGISTER</span><h1>Asset Intelligence</h1></div><p>Identity is preserved as <code>EntityType:EntityUid</code></p></section><div className="list-tools"><div className="segment-control"><button type="button" aria-pressed={assetClass === "equipment"} className={assetClass === "equipment" ? "active" : ""} onClick={() => chooseClass("equipment")}>Equipment</button><button type="button" aria-pressed={assetClass === "location"} className={assetClass === "location" ? "active" : ""} onClick={() => chooseClass("location")}>Locations</button></div>{page && <Pagination data={{ ...page, setOffset }} />}</div><div className="asset-layout"><aside className="asset-register"><div className="register-head"><strong>RANKED {assetClass.toUpperCase()}</strong><span>{page?.total ?? 0}</span></div><AssetList data={{ assets: page?.items ?? [], selected, select }} /></aside><section className="panel asset-detail"><AssetSelection assetKey={selected} /></section></div></div>;
}
