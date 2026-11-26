import { describe, expect, it } from "vitest";

import { formatUpdateError } from "./updateErrors";

describe("formatUpdateError", () => {
  it("uses the message from an Error", () => {
    expect(formatUpdateError(new Error("Signature verification failed"))).toBe(
      "Signature verification failed"
    );
  });

  it("falls back to the error name", () => {
    const err = new Error();
    err.name = "UpdaterError";
    expect(formatUpdateError(err)).toBe("UpdaterError");
  });

  it("accepts plain strings", () => {
    expect(formatUpdateError("offline")).toBe("offline");
  });

  it("unwraps an object message", () => {
    expect(formatUpdateError({ message: "bad signature" })).toBe("bad signature");
  });

  it("has a stable fallback for unknown shapes", () => {
    for (const value of [null, undefined, 0, false, "", {}, { code: 42 }]) {
      expect(formatUpdateError(value)).toBe("Update failed");
    }
  });
});
