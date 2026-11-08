import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ProviderHealth, sourceOutdated } from "./provider-health";
afterEach(cleanup);
const t = (_he: string, en: string) => en;
it("labels cached portal data outdated after a failed refresh, including when disconnected", () => {
  const source = { connected: false, last_success: 1793620000, error: "feed_unavailable", stale: true };
  render(<ProviderHealth name="Student portal" source={source} t={t} />);
  expect(screen.getByText("Student portal")).toBeInTheDocument();
  expect(screen.getByText("Outdated data")).toBeInTheDocument();
  expect(sourceOutdated(source)).toBe(true);
});
it("does not claim connected while loading or after an initial disconnection", () => {
  const { rerender } = render(<ProviderHealth name="Student portal" source={null} t={t} />);
  expect(screen.getByText("Loading…")).toBeInTheDocument();
  rerender(<ProviderHealth name="Student portal" source={{ connected: false, last_success: null }} t={t} />);
  expect(screen.getByText("Disconnected")).toBeInTheDocument();
  expect(sourceOutdated({ connected: false, last_success: null })).toBe(false);
});
