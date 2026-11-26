// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Tooltip } from "./Tooltip";

describe("Tooltip", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the label on hover and hides it on leave", async () => {
    vi.useFakeTimers();
    render(
      <Tooltip label="Remove file">
        <button type="button">x</button>
      </Tooltip>
    );
    const trigger = screen.getByRole("button", { name: "x" });
    fireEvent.mouseEnter(trigger);
    await vi.advanceTimersByTimeAsync(200);
    expect(screen.getByRole("tooltip").textContent).toContain("Remove file");
    fireEvent.mouseLeave(trigger);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("shows the label on keyboard focus and links it with aria-describedby", async () => {
    render(
      <Tooltip label="Close panel">
        <button type="button">close</button>
      </Tooltip>
    );
    const trigger = screen.getByRole("button", { name: "close" });
    fireEvent.focus(trigger);
    const tip = await screen.findByRole("tooltip");
    expect(tip.textContent).toContain("Close panel");
    expect(trigger.getAttribute("aria-describedby")).toBe(tip.id);
  });

  it("clears pending timers on unmount", () => {
    vi.useFakeTimers();
    const { unmount } = render(
      <Tooltip label="Hint">
        <button type="button">hint</button>
      </Tooltip>
    );
    fireEvent.mouseEnter(screen.getByRole("button", { name: "hint" }));
    unmount();
    expect(() => vi.runAllTimers()).not.toThrow();
  });
});
