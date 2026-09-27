import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("learning entry stylesheet", () => {
  it("does not depend on render-blocking remote font stylesheets", () => {
    const styles = readFileSync("src/styles.css", "utf8");
    expect(styles).not.toMatch(/@import\s+(?:url\()?["']?https?:/i);
    expect(styles).toContain("sans-serif");
  });
});
