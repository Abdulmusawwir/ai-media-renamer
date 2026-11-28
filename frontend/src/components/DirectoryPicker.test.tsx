// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import { readRecentDirs } from "./DirectoryPicker";

const KEY = "amr:recent-dirs";

describe("readRecentDirs", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns nothing when storage is empty", () => {
    expect(readRecentDirs()).toEqual([]);
  });

  it("migrates legacy string entries", () => {
    localStorage.setItem(KEY, JSON.stringify(["C:\\media", "/home/user/video"]));
    expect(readRecentDirs()).toEqual([
      { path: "C:\\media", at: 0 },
      { path: "/home/user/video", at: 0 },
    ]);
  });

  it("keeps timestamps on current entries", () => {
    localStorage.setItem(KEY, JSON.stringify([{ path: "D:\\clips", at: 1700000000000 }]));
    expect(readRecentDirs()).toEqual([{ path: "D:\\clips", at: 1700000000000 }]);
  });

  it("drops values that are not plausible absolute paths", () => {
    localStorage.setItem(
      KEY,
      JSON.stringify([
        { path: "relative/folder", at: 1 },
        { path: "javascript:alert(1)", at: 1 },
        { path: 42, at: 1 },
        { path: "C:\\ok", at: 1 },
      ])
    );
    expect(readRecentDirs()).toEqual([{ path: "C:\\ok", at: 1 }]);
  });

  it("survives malformed storage", () => {
    localStorage.setItem(KEY, "{not json");
    expect(readRecentDirs()).toEqual([]);
    localStorage.setItem(KEY, JSON.stringify({ nope: true }));
    expect(readRecentDirs()).toEqual([]);
  });

  it("caps the list", () => {
    const many = Array.from({ length: 20 }, (_, i) => ({
      path: `C:\\dir${i}`,
      at: i,
    }));
    localStorage.setItem(KEY, JSON.stringify(many));
    expect(readRecentDirs()).toHaveLength(8);
  });
});
