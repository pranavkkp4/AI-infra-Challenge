import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { App } from "./App";
import { apiPatch, setOperatorKey } from "./api";
import type { DashboardData } from "./types";

const dashboard: DashboardData = {
  dataset_label: "Synthetic Demo Dataset",
  metrics: {
    total_work_orders: 222,
    unique_assets: 74,
    recurring_incidents: 20,
    high_risk_assets: 1,
    human_review_count: 181,
    average_confidence: 0.72,
    repeat_incident_rate: 0.1,
    issue_resolution_rate: 0.2,
    mean_time_between_repeats: 34,
  },
  incidents_over_time: [],
  issue_distribution: [],
  high_risk_assets: [],
  recurrence_trends: [],
  department_activity: [],
  patterns: [],
};

const health = {
  status: "operational",
  database: "duckdb",
  demo_mode: true,
  dataset_label: "Synthetic Demo Dataset",
  analysis_start: "2022-01-01T00:00:00",
  analysis_end: "2025-02-01T00:00:00",
  review_threshold: 0.72,
};

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("application integration", () => {
  it("renders the API-backed executive route and navigation", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const payload = String(input).endsWith("/dashboard") ? dashboard : health;
      return new Response(JSON.stringify(payload), { status: 200 });
    }));

    render(<MemoryRouter><App /></MemoryRouter>);

    expect(await screen.findByText("Infrastructure signals,")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Review Queue/i })).toBeTruthy();
    expect(screen.getByText("222")).toBeTruthy();
  });

  it("adds the session operator key to mutations", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ status: "updated" })));
    vi.stubGlobal("fetch", fetchMock);
    setOperatorKey("operator-secret");

    await apiPatch("/reviews/INS-1", { decision: "CONFIRMED" });

    const request = fetchMock.mock.calls[0]?.[1];
    expect(new Headers(request?.headers).get("X-CivicOps-Key")).toBe("operator-secret");
  });
});
