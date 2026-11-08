"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Translate } from "@/lib/types";
import { Button } from "./ui/button";

export function AccountSecurity({ csrf, t }: { csrf: string; t: Translate }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <section className="panel">
    <h2>{t("סיסמת החשבון", "Account password")}</h2>
    <p className="field-help">{t("שינוי הסיסמה ינתק את החשבון מכל המכשירים. בחרו לפחות 8 תווים.", "Changing your password signs this account out on every device. Use at least 8 characters.")}</p>
    <form className="form-stack" onSubmit={async event => {
      event.preventDefault();
      const values = new FormData(event.currentTarget);
      if (values.get("new_password") !== values.get("confirm")) { setError(t("הסיסמאות אינן תואמות.", "Passwords do not match.")); return; }
      setBusy(true); setError("");
      try {
        await api("accounts/password", "PUT", { current_password: values.get("current_password"), new_password: values.get("new_password") }, csrf);
        window.location.reload();
      } catch { setError(t("לא ניתן לשנות את הסיסמה. בדקו את הסיסמה הנוכחית ואת החיבור.", "Could not change password. Check your current password and connection.")); }
      finally { setBusy(false); }
    }}>
      <label>{t("סיסמה נוכחית", "Current password")}<input type="password" name="current_password" required minLength={8} maxLength={1024} autoComplete="current-password" disabled={busy} dir="ltr" /></label>
      <label>{t("סיסמה חדשה", "New password")}<input type="password" name="new_password" required minLength={8} maxLength={1024} autoComplete="new-password" disabled={busy} dir="ltr" /></label>
      <label>{t("אימות סיסמה חדשה", "Confirm new password")}<input type="password" name="confirm" required minLength={8} maxLength={1024} autoComplete="new-password" disabled={busy} dir="ltr" /></label>
      {error && <p role="alert" className="error-message">{error}</p>}
      <Button type="submit" disabled={busy}>{t("עדכון הסיסמה", "Change password")}</Button>
    </form>
  </section>;
}
