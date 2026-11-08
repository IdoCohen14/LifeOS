import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PlanningBriefing } from "./planning-briefing";

afterEach(cleanup);

it("labels an ongoing overnight event with its real start date while navigating to today", () => {
  const onDay = vi.fn();
  render(
    <PlanningBriefing
      tasks={[]}
      events={[
        {
          id: "overnight",
          title: "Overnight fixture",
          notes: "",
          created_at: "",
          start: "2026-10-25T20:00:00Z",
          end: "2026-10-26T12:00:00Z",
          all_day: false,
        },
      ]}
      now={new Date("2026-10-26T10:00:00Z")}
      settings={{
        language: "en",
        theme: "dark",
        timezone: "Asia/Jerusalem",
        display_name: "",
      }}
      stale={false}
      t={(_he, en) => en}
      onDay={onDay}
      onTask={vi.fn()}
      onTasks={vi.fn()}
    />,
  );
  expect(screen.getByText("Happening now")).toBeVisible();
  const event = screen.getByRole("button", { name: /Overnight fixture/ });
  expect(event).toHaveTextContent("Sun 25 Oct");
  expect(event).toHaveTextContent("22:00");
  event.click();
  expect(onDay).toHaveBeenCalledWith("2026-10-26");
});
