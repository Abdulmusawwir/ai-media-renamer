// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import {
  basename,
  forgetFileStatus,
  initialFileStatus,
  markFileStatus,
  mergeLiveResult,
  sessionKey,
} from "./analysisResults";

describe("basename", () => {
  it("handles Windows and POSIX separators", () => {
    expect(basename("C:\\media\\clip.mp4")).toBe("clip.mp4");
    expect(basename("/home/user/clip.mp4")).toBe("clip.mp4");
    expect(basename("clip.mp4")).toBe("clip.mp4");
  });
});

describe("initialFileStatus", () => {
  it("marks every file queued by full path", () => {
    expect(initialFileStatus(["C:\\a\\one.mp4", "/b/two.wav"])).toEqual({
      "C:\\a\\one.mp4": "queued",
      "/b/two.wav": "queued",
    });
  });

  it("returns an empty map for no files", () => {
    expect(initialFileStatus([])).toEqual({});
  });
});

describe("mergeLiveResult", () => {
  it("adds one card per original path", () => {
    const next = mergeLiveResult({}, {
      original_path: "C:\\a\\one.mp4",
      original_name: "one.mp4",
      staged_name: "Sunset-Drone",
      category: "footage",
      tags: ["aerial", "sunset"],
      summary: "A drone shot.",
    });
    expect(Object.keys(next)).toEqual(["C:\\a\\one.mp4"]);
    expect(next["C:\\a\\one.mp4"]).toEqual({
      originalName: "one.mp4",
      stagedName: "Sunset-Drone",
      category: "footage",
      tags: ["aerial", "sunset"],
      summary: "A drone shot.",
    });
  });

  it("replaces the same path instead of duplicating it", () => {
    const first = mergeLiveResult({}, {
      original_path: "p.mp4",
      staged_name: "First",
    });
    const second = mergeLiveResult(first, {
      original_path: "p.mp4",
      staged_name: "Second",
    });
    expect(Object.keys(second)).toHaveLength(1);
    expect(second["p.mp4"].stagedName).toBe("Second");
  });

  it("ignores events without a path", () => {
    const prev = { keep: { originalName: "k", stagedName: "", category: "c", tags: [], summary: "" } };
    expect(mergeLiveResult(prev, undefined)).toBe(prev);
    expect(mergeLiveResult(prev, { staged_name: "no path" })).toBe(prev);
  });

  it("fills safe defaults for a sparse event", () => {
    const next = mergeLiveResult({}, { original_path: "x.mov" });
    expect(next["x.mov"]).toEqual({
      originalName: "x.mov",
      stagedName: "",
      category: "uncategorized",
      tags: [],
      summary: "",
    });
  });
});

describe("file status transitions", () => {
  it("keeps same-named files apart by full path", () => {
    let status = initialFileStatus(["C:\\A\\clip.mp4", "C:\\B\\clip.mp4"]);
    expect(status["C:\\A\\clip.mp4"]).toBe("queued");
    status = markFileStatus(status, "C:\\A\\clip.mp4", "failed");
    expect(status).toEqual({
      "C:\\A\\clip.mp4": "failed",
      "C:\\B\\clip.mp4": "queued",
    });
  });

  it("moves a file from queued to done and failed", () => {
    let status = initialFileStatus(["C:\\a\\one.mp4"]);
    status = markFileStatus(status, "C:\\a\\one.mp4", "done");
    expect(status["C:\\a\\one.mp4"]).toBe("done");
    status = markFileStatus(status, "C:\\a\\one.mp4", "failed");
    expect(status["C:\\a\\one.mp4"]).toBe("failed");
  });

  it("forgets a removed file and keeps the rest", () => {
    const status = { "one.mp4": "done" as const, "two.mp4": "queued" as const };
    const next = forgetFileStatus(status, "one.mp4");
    expect(next).toEqual({ "two.mp4": "queued" });
  });

  it("returns the same map when nothing is removed", () => {
    const status = { "one.mp4": "done" as const };
    expect(forgetFileStatus(status, "missing.mp4")).toBe(status);
  });
});

describe("sessionKey", () => {
  it("prefers the name, then the filename from the path", () => {
    expect(sessionKey({ name: "session-1", path: "C:\\s\\session-1.json" })).toBe("session-1");
    expect(sessionKey({ path: "C:\\s\\session-2.json" })).toBe("session-2.json");
    expect(sessionKey({})).toBe("");
  });
});
