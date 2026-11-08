import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Login } from "./workspace";

it("collects account identity and checks password confirmation before registration", async () => {
  const login = vi.fn(async () => {});
  render(<Login accountMode onLogin={login} />);
  fireEvent.change(screen.getByLabelText("שם משתמש"), { target: { value: "fixture-user" } });
  fireEvent.change(screen.getByLabelText("הסיסמה שלך"), { target: { value: "fixture password" } });
  fireEvent.click(screen.getByRole("button", { name: "יצירת חשבון חדש" }));
  fireEvent.change(screen.getByLabelText("אימות סיסמה"), { target: { value: "different password" } });
  fireEvent.submit(screen.getByRole("button", { name: "צור חשבון" }).closest("form")!);
  expect(login).not.toHaveBeenCalled();
  expect(screen.getByRole("alert").textContent).toContain("הסיסמאות אינן תואמות");
  fireEvent.change(screen.getByLabelText("אימות סיסמה"), { target: { value: "fixture password" } });
  fireEvent.submit(screen.getByRole("button", { name: "צור חשבון" }).closest("form")!);
  await waitFor(() => expect(login).toHaveBeenCalledWith("fixture password", "fixture-user", true));
});
