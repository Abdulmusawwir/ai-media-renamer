// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({
  authHeaders: () => ({}),
  browseFolder: vi.fn(async () => ({
    path: "C:\\Work",
    parent: "C:\\",
    drives: ["C:\\"],
    folders: [{ name: "Projects", path: "C:\\Work\\Projects", kind: "folder" }],
    files: [
      {
        name: "keep.jpg",
        path: "C:\\Work\\keep.jpg",
        kind: "image",
        is_media: true,
        size: 10,
      },
      {
        name: "other.txt",
        path: "C:\\Work\\other.txt",
        kind: "other",
        is_media: false,
        size: 10,
      },
    ],
  })),
}));

vi.mock("../store", () => ({
  useToast: () => ({ error: vi.fn(), info: vi.fn(), success: vi.fn() }),
}));

import DirectoryPicker from "./DirectoryPicker";

afterEach(cleanup);

describe("DirectoryPicker filter and breadcrumbs", () => {
  it("filters entries by name and reports no matches", async () => {
    render(<DirectoryPicker onAddFile={vi.fn()} />);
    const filter = await screen.findByPlaceholderText("Filter this folder by name");

    fireEvent.change(filter, { target: { value: "keep" } });
    expect(screen.getByText("keep.jpg")).toBeTruthy();
    expect(screen.queryByText("other.txt")).toBeNull();

    fireEvent.change(filter, { target: { value: "zzz" } });
    expect(screen.getByText("No matching files here.")).toBeTruthy();
  });

  it("renders clickable path segments", async () => {
    render(<DirectoryPicker onAddFile={vi.fn()} />);
    expect(await screen.findByTitle("C:\\Work")).toBeTruthy();
  });
});
