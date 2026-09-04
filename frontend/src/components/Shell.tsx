import { NavLink, Outlet, useLocation } from "react-router-dom";

import { setOperatorKey, useApi } from "../api";

const navigation = [
  { path: "/", code: "01", label: "Executive" },
  { path: "/incidents", code: "02", label: "Incidents" },
  { path: "/assets", code: "03", label: "Assets" },
  { path: "/investigations", code: "04", label: "Investigation" },
  { path: "/reviews", code: "05", label: "Review Queue" },
  { path: "/reports", code: "06", label: "Reports + Search" },
];

function Navigation() {
  return (
    <nav className="primary-nav" aria-label="Primary navigation">
      {navigation.map((item) => (
        <NavLink key={item.path} to={item.path} end={item.path === "/"}>
          <span>{item.code}</span>
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

function SystemStatus() {
  const { data, error } = useApi<{ status: string; database: string }>("/health");
  return (
    <div className="system-status">
      <span className={error ? "status-dot error" : "status-dot"} />
      <div>
        <strong>{error ? "API OFFLINE" : data?.status.toUpperCase() ?? "CONNECTING"}</strong>
        <small>{data ? `${data.database} / local` : "checking service"}</small>
      </div>
    </div>
  );
}

export function Shell() {
  const location = useLocation();
  const { data: metadata } = useApi<{
    demo_mode: boolean;
    dataset_label: string;
    analysis_start: string | null;
    analysis_end: string | null;
  }>("/health");
  const active = navigation.find((item) =>
    item.path === "/" ? location.pathname === "/" : location.pathname.startsWith(item.path),
  );
  const enterAccessKey = () => {
    const key = window.prompt("Enter the CivicOps operator access key");
    if (key?.trim()) {
      setOperatorKey(key.trim());
      window.location.reload();
    }
  };
  return (
    <div className="app-frame">
      <aside className="sidebar">
        <div className="brand-mark">
          <span className="brand-seal">CO</span>
          <div><strong>CIVIC//OPS</strong><small>INFRA INTELLIGENCE</small></div>
        </div>
        <Navigation />
        <div className="sidebar-foot">
          <SystemStatus />
          <p>Decision support only.<br />Human authorization required.</p>
        </div>
      </aside>
      <div className="workspace">
        <div className="demo-ribbon">
          {metadata?.dataset_label.toUpperCase() ?? "DATASET CONNECTING"} <span>//</span>
          {metadata?.demo_mode ? "TRAINING ENVIRONMENT" : "CONTROLLED OPERATIONAL DATA"}
          <span>//</span> NOT FIELD AUTHORIZATION
        </div>
        <header className="topbar">
          <div><small>OPERATIONS DESK / {active?.code}</small><strong>{active?.label}</strong></div>
          <div className="topbar-actions">
            {metadata && !metadata.demo_mode && <button onClick={enterAccessKey}>Set access key</button>}
            <div className="topbar-meta"><span>ANALYSIS WINDOW</span><strong>{formatWindow(metadata)}</strong></div>
          </div>
        </header>
        <main className="main-content"><Outlet /></main>
      </div>
    </div>
  );
}

function formatWindow(metadata: { analysis_start: string | null; analysis_end: string | null } | null): string {
  if (!metadata?.analysis_start || !metadata.analysis_end) return "PENDING";
  const start = metadata.analysis_start.slice(0, 7).replace("-", ".");
  const end = metadata.analysis_end.slice(0, 7).replace("-", ".");
  return `${start} - ${end}`;
}
