"use client";
import { useState } from "react";
import type { Translate } from "@/lib/types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

export function Reauthenticate({
  t,
  onLogin,
  onCancel,
}: {
  t: Translate;
  onLogin: (password: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Modal
      open
      onClose={() => {
        if (!busy) onCancel();
      }}
      title={t("כניסה מחדש", "Sign in again")}
      description={t(
        "תוקף החיבור פג. הטיוטה שלך נשמרת בחלון שמאחור.",
        "Your session expired. Your draft is still open behind this window.",
      )}
      closeLabel={t("סגירה", "Close")}
    >
      <form
        className="form-stack"
        onSubmit={async (e) => {
          e.preventDefault();
          const password = String(
            new FormData(e.currentTarget).get("password"),
          );
          setBusy(true);
          setError("");
          try {
            await onLogin(password);
          } catch {
            setError(
              t(
                "הכניסה נכשלה. בדקו את הסיסמה ונסו שוב.",
                "Sign in failed. Check your password and retry.",
              ),
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          {t("הסיסמה שלך", "Your password")}
          <input
            name="password"
            type="password"
            required
            autoComplete="current-password"
            dir="ltr"
          />
        </label>
        {error && (
          <p className="error-message" role="alert">
            {error}
          </p>
        )}
        <Button type="submit" disabled={busy}>
          {busy
            ? t("מתחבר…", "Signing in…")
            : t("כניסה ושמירת הטיוטה", "Sign in and keep draft")}
        </Button>
      </form>
    </Modal>
  );
}
