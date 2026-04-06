import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CollapsibleSection } from "@/components/results/CollapsibleSection";

describe("CollapsibleSection", () => {
  it("renders the section title", () => {
    render(
      <CollapsibleSection title="Statistical Detail">
        <p>Content here</p>
      </CollapsibleSection>
    );
    expect(screen.getByText("Statistical Detail")).toBeInTheDocument();
  });

  it("hides children when defaultOpen is false (default)", () => {
    render(
      <CollapsibleSection title="Hidden Section">
        <p>Hidden content</p>
      </CollapsibleSection>
    );
    expect(screen.queryByText("Hidden content")).not.toBeInTheDocument();
  });

  it("shows children when defaultOpen is true", () => {
    render(
      <CollapsibleSection title="Open Section" defaultOpen>
        <p>Visible content</p>
      </CollapsibleSection>
    );
    expect(screen.getByText("Visible content")).toBeInTheDocument();
  });

  it("expands when the header button is clicked", async () => {
    const user = userEvent.setup();
    render(
      <CollapsibleSection title="Toggle Section">
        <p>Toggled content</p>
      </CollapsibleSection>
    );
    expect(screen.queryByText("Toggled content")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button"));
    expect(screen.getByText("Toggled content")).toBeInTheDocument();
  });

  it("collapses when clicked again", async () => {
    const user = userEvent.setup();
    render(
      <CollapsibleSection title="Toggle Section" defaultOpen>
        <p>Collapsible content</p>
      </CollapsibleSection>
    );
    expect(screen.getByText("Collapsible content")).toBeInTheDocument();
    await user.click(screen.getByRole("button"));
    expect(screen.queryByText("Collapsible content")).not.toBeInTheDocument();
  });

  it("sets aria-expanded correctly", async () => {
    const user = userEvent.setup();
    render(
      <CollapsibleSection title="Aria Test">
        <p>Content</p>
      </CollapsibleSection>
    );
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
  });

  it("renders an optional badge next to the title", () => {
    render(
      <CollapsibleSection title="With Badge" badge={<span>New</span>}>
        <p>Content</p>
      </CollapsibleSection>
    );
    expect(screen.getByText("New")).toBeInTheDocument();
  });
});
