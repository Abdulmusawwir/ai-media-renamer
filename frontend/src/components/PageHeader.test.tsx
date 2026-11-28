// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { UploadCloud } from "lucide-react";
import { afterEach, describe, expect, it } from "vitest";

import { PageHeader } from "./PageHeader";

afterEach(cleanup);

describe("PageHeader", () => {
  it("shows title, description and action", () => {
    render(
      <PageHeader
        icon={UploadCloud}
        title="Analysis Wizard"
        description="Add media and run the pipeline."
        action={<button type="button">Run</button>}
      />
    );
    expect(screen.getByRole("heading", { name: "Analysis Wizard" })).toBeTruthy();
    expect(screen.getByText("Add media and run the pipeline.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run" })).toBeTruthy();
  });

  it("omits the action when not supplied", () => {
    render(<PageHeader icon={UploadCloud} title="Models" />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
