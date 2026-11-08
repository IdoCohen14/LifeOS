import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import { AccountRecoverySettings } from "./account-recovery-settings";

vi.mock("@/lib/api", async () => ({ ...await vi.importActual("@/lib/api"), api: vi.fn() }));
vi.mock("./scheduled-backup-settings", () => ({ ScheduledBackupSettings: () => null }));
afterEach(cleanup);

it.each([409, 401])("requires another review after confirmation fails with %i", async status => {
  const unauthorized = vi.fn();
  const restored = vi.fn();
  vi.mocked(api).mockClear();
  vi.mocked(api).mockImplementation(async path => {
    if (path === "recovery/backups") return [{ id: "fixture", created_at: "2026-10-30T08:00:00Z", size: 1024 }];
    if (path.endsWith("restore-preview")) return { id: "expired-preview", counts: { tasks: 2, events: 0, courses: 0, documents: 0 } };
    if (path.endsWith("confirm")) throw new ApiError(status, "fixture-rejection");
    throw new Error(path);
  });
  render(<AccountRecoverySettings csrf="fixture-csrf" settings={{ display_name: "", language: "he", theme: "dark", timezone: "Asia/Jerusalem" }} t={he => he} onUnauthorized={unauthorized} onRestored={restored} />);
  fireEvent.click(await screen.findByRole("button", { name: "בדיקה ושחזור" }));
  fireEvent.change(screen.getByLabelText("סיסמת הגיבוי לשחזור"), { target: { value: "fixture password" } });
  fireEvent.click(screen.getByRole("button", { name: "בדיקת הגיבוי" }));
  fireEvent.click(await screen.findByRole("button", { name: "אישור שחזור החשבון" }));
  await screen.findByRole("button", { name: "בדיקת הגיבוי" });
  expect(screen.queryByRole("button", { name: "אישור שחזור החשבון" })).toBeNull();
  expect(restored).not.toHaveBeenCalled();
  expect(unauthorized).toHaveBeenCalledTimes(status === 401 ? 1 : 0);
  fireEvent.click(screen.getByRole("button", { name: "ביטול" }));
  fireEvent.click(screen.getByRole("button", { name: "בדיקה ושחזור" }));
  expect(screen.getByLabelText("סיסמת הגיבוי לשחזור")).toHaveValue("");
  expect(screen.queryByRole("button", { name: "אישור שחזור החשבון" })).toBeNull();
});

it("requires review before confirming an account restore", async () => {
  const restored = vi.fn();
  vi.mocked(api).mockImplementation(async path => {
    if (path === "recovery/backups") return [{ id: "backup-fixture", created_at: "2026-10-30T08:00:00Z", size: 1024 }];
    if (path.endsWith("restore-preview")) return { id: "preview-fixture", counts: { tasks: 2, events: 1, courses: 1, documents: 0 } };
    if (path.endsWith("confirm")) return { restored: true };
    throw new Error(path);
  });
  render(<AccountRecoverySettings csrf="fixture-csrf" settings={{ display_name: "", language: "he", theme: "dark", timezone: "Asia/Jerusalem" }} t={he => he} onUnauthorized={vi.fn()} onRestored={restored} />);
  fireEvent.click(await screen.findByRole("button", { name: "בדיקה ושחזור" }));
  fireEvent.change(screen.getByLabelText("סיסמת הגיבוי לשחזור"), { target: { value: "fixture password" } });
  fireEvent.click(screen.getByRole("button", { name: "בדיקת הגיבוי" }));
  await screen.findByRole("button", { name: "אישור שחזור החשבון" });
  expect(vi.mocked(api).mock.calls.some(([path]) => path.endsWith("confirm"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "אישור שחזור החשבון" }));
  await waitFor(() => expect(restored).toHaveBeenCalledOnce());
  expect(api).toHaveBeenCalledWith("recovery/restore/preview-fixture/confirm", "POST", { password: "fixture password" }, "fixture-csrf");
});
