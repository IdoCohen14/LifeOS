import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { WeeklyReview } from "./weekly-review";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: vi.fn(),
  ApiError: class extends Error {
    status = 503;
  },
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
it("does not fetch or invent completion counts until the review is opened", async () => {
  vi.mocked(api).mockRejectedValue(Error("offline"));
  render(
    <WeeklyReview
      settings={{
        display_name: "",
        language: "en",
        theme: "dark",
        timezone: "Asia/Jerusalem",
      }}
      revision={0}
      t={(_he, en) => en}
      onTask={vi.fn()}
      onUnauthorized={vi.fn()}
    />,
  );
  expect(api).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Show review" }));
  await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());
  expect(screen.queryByText("0")).not.toBeInTheDocument();
});
