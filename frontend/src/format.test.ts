import { describe, expect, it } from "vitest";

import { days, label, percent, riskBand, shortDate } from "./format";

describe("format helpers", () => {
  it("formats canonical issue labels and scores", () => {
    expect(label("low_pressure")).toBe("Low Pressure");
    expect(percent(0.724)).toBe("72%");
  });

  it("assigns deterministic risk bands", () => {
    expect(riskBand(65)).toBe("critical");
    expect(riskBand(40)).toBe("watch");
    expect(riskBand(39)).toBe("stable");
  });

  it("handles missing dates", () => {
    expect(shortDate(null)).toBe("Not recorded");
    expect(shortDate("not-a-date")).toBe("Invalid date");
  });

  it("labels observed intervals without implying a recommendation", () => {
    expect(days(1)).toBe("1 day");
    expect(days(34.4)).toBe("34 days");
    expect(days(null)).toBe("Not available");
  });
});
