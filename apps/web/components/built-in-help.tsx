"use client";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Translate } from "@/lib/types";
import { Button } from "./ui/button";

type Catalog = { source: "built_in"; topics: { id: string; label: [string,string]; answer: [string,string] }[] };
export function BuiltInHelp({ t, onUnauthorized }: { t: Translate; onUnauthorized: () => void }) {
  const [data, setData] = useState<Catalog | null>(null);
  const [topic, setTopic] = useState("planning");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  async function load() {
    if (busy) return;
    setBusy(true); setError(false);
    try { const next = await api<Catalog>("assistant/help"); if (next.source !== "built_in") throw Error("invalid_help_source"); setData(next); }
    catch (error) { if (error instanceof ApiError && error.status === 401) onUnauthorized(); setError(true); }
    finally { setBusy(false); }
  }
  const selected = data?.topics.find(value => value.id === topic) ?? data?.topics[0];
  return <details className="assistant-history assistant-help" onToggle={event => { if (event.currentTarget.open && !data && !busy) void load(); }}>
    <summary>{t("עזרה מובנית באפליקציה", "Built-in app help")}</summary>
    <p className="field-help">{t("הוראות שימוש מוכנות, בלי להפעיל מודל ובלי לקרוא מידע אישי. זמינות גם כשהעוזר המקומי אינו מחובר.", "Curated instructions without starting a model or reading personal records. Available even when the local assistant is offline.")}</p>
    {data && <><label>{t("נושא לעזרה", "Help topic")}<select aria-label={t("נושא לעזרה", "Help topic")} value={selected?.id ?? ""} onChange={event => setTopic(event.target.value)} disabled={busy}>{data.topics.map(value => <option key={value.id} value={value.id}>{t(...value.label)}</option>)}</select></label>{selected && <p className="help-answer" aria-live="polite">{t(...selected.answer)}</p>}</>}
    {error && <p role="alert">{t("לא ניתן לטעון את מדריכי השימוש כרגע. נסו רענון; לא הופעל מודל.", "Instructions are unavailable. Try refreshing; no model was started.")}</p>}
    <Button size="small" variant="ghost" disabled={busy} onClick={() => void load()}>{busy ? t("טוען…", "Loading…") : t("רענון העזרה", "Refresh help")}</Button>
  </details>;
}
