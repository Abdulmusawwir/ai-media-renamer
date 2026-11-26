// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { checkForUpdate } = vi.hoisted(() => ({ checkForUpdate: vi.fn() }));

vi.mock("../desktop", () => ({
  isDesktop: true,
  desktop: {
    invoke: vi.fn(async (cmd: string) =>
      cmd === "get_shell_settings" ? { close_to_tray: true } : undefined
    ),
    listen: vi.fn(async () => () => undefined),
    checkForUpdate,
    downloadAndInstall: vi.fn(async () => undefined),
    relaunch: vi.fn(async () => undefined),
  },
}));

vi.mock("../hooks/api", () => ({
  useConfig: () => ({
    data: { model: {}, prompt_profiles: { profiles: {} } },
    dataUpdatedAt: 0,
    isLoading: false,
    refetch: vi.fn(),
  }),
  usePutConfig: () => ({ mutateAsync: vi.fn(async (v: unknown) => v) }),
}));

vi.mock("../store", () => ({
  useStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      config: { model: {}, prompt_profiles: { profiles: {} } },
      setConfig: vi.fn(),
      pendingUpdateCheck: false,
      setPendingUpdateCheck: vi.fn(),
    }),
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

import Settings from "./Settings";

describe("Settings update errors", () => {
  beforeEach(() => {
    checkForUpdate.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("shows a failed check instead of saying everything is up to date", async () => {
    checkForUpdate.mockRejectedValueOnce(new Error("bad signature"));
    render(<Settings />);
    const button = screen.getByRole("button", { name: /check for updates/i });
    fireEvent.click(button);
    await waitFor(() => {
      expect(screen.getByText("bad signature")).toBeTruthy();
    });
    expect(screen.queryByText("You're up to date.")).toBeNull();
  });

  it("still reports when there is no update", async () => {
    checkForUpdate.mockResolvedValueOnce(null);
    render(<Settings />);
    fireEvent.click(screen.getByRole("button", { name: /check for updates/i }));
    await waitFor(() => {
      expect(screen.getByText("You're up to date.")).toBeTruthy();
    });
  });
});
