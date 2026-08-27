import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { MessageBody } from "./MessageBody";

describe("MessageBody", () => {
  it("renders the Markdown a model writes instead of its punctuation", () => {
    const { container } = render(
      <MessageBody text={"Spread is the **difference** between *bid* and `ask`."} />,
    );

    expect(container.querySelector("strong")).toHaveTextContent("difference");
    expect(container.querySelector("em")).toHaveTextContent("bid");
    expect(container.querySelector("code")).toHaveTextContent("ask");
    expect(container.textContent).not.toContain("**");
  });

  it("renders lists as lists", () => {
    const { container } = render(<MessageBody text={"- one\n- two\n- three"} />);
    expect(container.querySelectorAll("li")).toHaveLength(3);
  });

  it("does not render raw HTML from a model, at all", () => {
    // The whole XSS argument for this component: `rehype-raw` is absent, so HTML is never built into
    // elements in the first place. If this fails, someone added it and the component is no longer safe.
    const { container } = render(
      <MessageBody text={'<img src=x onerror="alert(1)"> and <b>bold</b>'} />,
    );

    // No elements were built from it, and no attribute came with it — the markup arrives
    // as escaped text, which is inert and still readable.
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("[onerror]")).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror="alert(1)">');
  });

  it("opens http links safely and refuses schemes that could act on the operator", () => {
    const { container } = render(
      <MessageBody
        text={"[docs](https://example.com) and [bad](javascript:alert(1)) and [file](data:text/html,x)"}
      />,
    );

    const links = [...container.querySelectorAll("a")];
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "https://example.com");
    expect(links[0]).toHaveAttribute("rel", "noopener noreferrer");
    expect(links[0]).toHaveAttribute("target", "_blank");
    // Refused, but not hidden — the operator still reads what the model wrote.
    expect(screen.getByText("bad")).toBeInTheDocument();
    expect(screen.getByText("file")).toBeInTheDocument();
  });

  it("shows a table in its own scroller rather than widening the bubble", () => {
    const { container } = render(
      <MessageBody text={"| a | b |\n| --- | --- |\n| 1 | 2 |"} />,
    );
    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    expect(table?.parentElement?.className).toContain("overflow-x-auto");
  });

  describe("mid-stream", () => {
    it("bolds an unfinished emphasis instead of showing its asterisks", () => {
      // Without `remend` CommonMark reads this as literal `**`, which is the flicker the
      // whole streaming path exists to avoid.
      const { container } = render(<MessageBody streaming text={"Spread is the **differen"} />);

      expect(container.querySelector("strong")).toHaveTextContent("differen");
      expect(container.textContent).not.toContain("**");
    });

    it("closes an unfinished inline code span", () => {
      const { container } = render(<MessageBody streaming text={"Try `pnpm de"} />);
      expect(container.querySelector("code")).toHaveTextContent("pnpm de");
    });

    it("leaves an unfinished link as text, with no placeholder href to click", () => {
      const { container } = render(<MessageBody streaming text={"see [the docs](https://exa"} />);

      expect(container.querySelector("a")).toBeNull();
      expect(container.textContent).toContain("the docs");
      // `linkMode: "text-only"` — the default would park it on a `streamdown:` URL.
      expect(container.innerHTML).not.toContain("streamdown:");
    });

    it("leaves a settled message alone", () => {
      // Not run through `remend` once complete: valid Markdown needs no repair, and
      // repairing it anyway is a chance to change text nothing asked to change.
      const { container } = render(<MessageBody text={"a lone ** stays a lone **"} />);
      expect(container.textContent).toContain("**");
    });

    it("does not turn a dollar amount into maths", () => {
      // `$` is ordinary vocabulary here — rates and costs are written this way all over
      // the agent's replies, so both KaTeX completions stay off.
      const { container } = render(<MessageBody streaming text={"that turn cost $0.2"} />);
      expect(container.textContent).toContain("$0.2");
    });
  });
});
