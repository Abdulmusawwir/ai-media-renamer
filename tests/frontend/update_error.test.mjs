import assert from "node:assert/strict";
import test from "node:test";

import { formatUpdateError } from "../../frontend/src/desktop/updateErrors.ts";

test("Error with a message is shown verbatim", () => {
  assert.equal(formatUpdateError(new Error("Signature verification failed")), "Signature verification failed");
});

test("Error without a message falls back to its name", () => {
  const err = new Error();
  err.name = "UpdaterError";
  assert.equal(formatUpdateError(err), "UpdaterError");
});

test("plain strings are shown verbatim", () => {
  assert.equal(formatUpdateError("offline"), "offline");
});

test("object with a message is unwrapped", () => {
  assert.equal(formatUpdateError({ message: "bad signature" }), "bad signature");
});

test("unknown shapes get a stable fallback", () => {
  assert.equal(formatUpdateError(null), "Update failed");
  assert.equal(formatUpdateError(undefined), "Update failed");
  assert.equal(formatUpdateError({ code: 42 }), "Update failed");
  assert.equal(formatUpdateError(0), "Update failed");
});
