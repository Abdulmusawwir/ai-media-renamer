// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Tooltip } from "./Tooltip";

describe("Tooltip", () => {
  afterEach(() => {
    cleanup();
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

  it("hides on blur and preserves the child's own handler", async () => {
    const onFocus = vi.fn();
    render(
      <Tooltip label="Settings tip">
        <button type="button" onFocus={onFocus}>settings</button>
      </Tooltip>
    );
    const trigger = screen.getByRole("button", { name: "settings" });
    fireEvent.focus(trigger);
    expect(onFocus).toHaveBeenCalledTimes(1);
    const tip = await screen.findByRole("tooltip");
    expect(tip.textContent).toContain("Settings tip");
    fireEvent.blur(trigger);
    expect(screen.queryByRole("tooltip")).toBeNull();
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
