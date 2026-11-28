// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { relativeFromIso, relativeTime } from "./relativeTime";

afterEach(() => {
  vi.useRealTimers();
});

describe("relativeTime", () => {
  it("returns nothing for a missing timestamp", () => {
    expect(relativeTime(0)).toBe("");
  });

  it("describes recent and older timestamps", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-28T12:00:00Z"));
    const now = Date.now();
    expect(relativeTime(now - 5_000)).toBe("just now");
    expect(relativeTime(now - 5 * 60_000)).toBe("5m ago");
    expect(relativeTime(now - 3 * 3_600_000)).toBe("3h ago");
    expect(relativeTime(now - 2 * 86_400_000)).toBe("2d ago");
  });

  it("never returns a negative age", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-28T12:00:00Z"));
    expect(relativeTime(Date.now() + 60_000)).toBe("just now");
  });
});

describe("relativeFromIso", () => {
  it("parses an ISO date", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-28T12:00:00Z"));
    expect(relativeFromIso("2026-11-28T09:00:00Z")).toBe("3h ago");
  });

  it("returns nothing for missing or invalid input", () => {
    expect(relativeFromIso(undefined)).toBe("");
    expect(relativeFromIso("not a date")).toBe("");
  });
});
