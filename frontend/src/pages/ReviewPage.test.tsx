import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import type { Insight, Page, ReviewItem } from "../types";

const insight: Insight = {
  insight_id: "INS-1",
  incident_id: "INC-1",
  title: "Low pressure · EQ-01",
  asset_key: "equipment:EQ-01",
  issue_family: "low_pressure",
  summary: "Repeated pressure complaints were grouped into one episode.",
  observations: ["Three records describe low pressure."],
  interpretation: "The issue appears in at least three work orders.",
  possible_cause: { statement: "Insufficient evidence to determine cause.", support_level: "UNKNOWN" },
  recommended_action: "Inspect the pressure regulation assembly.",
  confidence: 0.61,
  confidence_level: "LOW",
  requires_human_review: true,
  supporting_work_orders: ["WO-1", "WO-2"],
  contradicting_work_orders: [],
  confidence_components: {
    semantic_consistency: 0.7,
    asset_consistency: 0.8,
    temporal_consistency: 0.6,
    evidence_strength: 0.65,
    issue_agreement: 0.7,
    conflict_penalty: 0,
    score: 0.61,
    level: "LOW",
    requires_human_review: true,
  },
  generated_by: "deterministic_alp",
};

const review: ReviewItem = {
  review_id: "REV-1",
  decision: "PENDING",
  reviewer_note: null,
  edited_issue_family: null,
  edited_recommendation: null,
  incident: {
    incident_id: "INC-1",
    asset_key: "equipment:EQ-01",
    issue_family: "low_pressure",
    department: "Water",
    first_seen: "2023-01-01T00:00:00",
    last_seen: "2023-02-01T00:00:00",
    work_order_count: 2,
    recurring: false,
    resolution_status: "UNKNOWN",
    confidence: 0.61,
    confidence_level: "LOW",
    requires_human_review: true,
    risk_score: 70,
  },
  insight,
};

const page: Page<ReviewItem> = { items: [review], total: 1, limit: 100, offset: 0 };
const health = {
  status: "operational",
  database: "duckdb",
  demo_mode: true,
  dataset_label: "Synthetic Demo Dataset",
  analysis_start: "2023-01-01T00:00:00",
  analysis_end: "2023-02-01T00:00:00",
  review_threshold: 0.72,
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("review editing", () => {
  it("submits issue family and recommendation edits with the decision", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "PATCH") return new Response(JSON.stringify({ status: "updated" }), { status: 200 });
      if (url.endsWith("/health")) return new Response(JSON.stringify(health), { status: 200 });
      if (url.includes("/reviews?")) return new Response(JSON.stringify(page), { status: 200 });
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter initialEntries={["/reviews"]}><App /></MemoryRouter>);

    fireEvent.change(await screen.findByLabelText("Edit issue family"), { target: { value: "water_leak" } });
    fireEvent.change(screen.getByLabelText("Edit recommendation"), { target: { value: "Schedule a valve inspection." } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm + save" }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true));
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")?.[1];
    expect(JSON.parse(String(patch?.body))).toMatchObject({
      decision: "CONFIRMED",
      edited_issue_family: "water_leak",
      edited_recommendation: "Schedule a valve inspection.",
    });
  });
});
