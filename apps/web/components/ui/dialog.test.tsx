import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { Modal } from "./dialog";

afterEach(cleanup);

function Fixture({ changed }: { changed: "removed" | "disabled" | "unchanged" }) {
  const [open, setOpen] = useState(false);
  const [finished, setFinished] = useState(false);
  return <main id="main-content" tabIndex={-1}>
    {!(finished && changed === "removed") && <button disabled={finished && changed === "disabled"} onClick={() => setOpen(true)}>Open fixture</button>}
    <Modal open={open} onClose={() => setOpen(false)} title="Fixture dialog" description="Synthetic focus check" closeLabel="Close fixture">
      <button onClick={() => { setFinished(true); setOpen(false); }}>Finish fixture</button>
    </Modal>
  </main>;
}

it.each(["removed", "disabled", "unchanged"] as const)("restores focus when the opener is %s", async changed => {
  render(<Fixture changed={changed} />);
  const opener = screen.getByRole("button", { name: "Open fixture" });
  opener.focus();
  fireEvent.click(opener);
  await screen.findByRole("dialog", { name: "Fixture dialog" });
  fireEvent.click(screen.getByRole("button", { name: "Finish fixture" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await waitFor(() => expect(changed === "unchanged" ? opener : screen.getByRole("main")).toHaveFocus());
});
