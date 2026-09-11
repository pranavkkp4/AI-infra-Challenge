import { afterEach, describe, expect, it, vi } from "vitest";

import { downloadReport } from "./api";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("report downloads", () => {
  it("keeps the object URL alive until the download anchor is removed", async () => {
    vi.useFakeTimers();
    const createObjectURL = vi.fn(() => "blob:civicops-report");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    await downloadReport("json");

    const anchor = document.querySelector<HTMLAnchorElement>("a[download='PM_INSIGHT_REPORT.json']");
    expect(anchor).toBeTruthy();
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(revokeObjectURL).not.toHaveBeenCalled();

    vi.runAllTimers();

    expect(revokeObjectURL).toHaveBeenCalledWith("blob:civicops-report");
    expect(anchor?.isConnected).toBe(false);
  });
});
