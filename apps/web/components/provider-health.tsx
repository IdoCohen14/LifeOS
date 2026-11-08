import type { Translate } from "@/lib/types";

export type SourceHealth = { connected: boolean; stale?: boolean; error?: string | null; last_success: number | null; state?: string; syncing?: boolean };
export function sourceOutdated(source: SourceHealth | null) {
  return !!source && (source.connected || source.last_success !== null) &&
    (!source.connected || source.stale || !!source.error);
}
export function ProviderHealth({ name, source, t }: { name: string; source: SourceHealth | null; t: Translate }) {
  const label = !source ? t("טוען…", "Loading…")
    : sourceOutdated(source) ? t("מידע לא מעודכן", "Outdated data")
      : source.syncing ? t("מסנכרן…", "Syncing…")
        : source.connected ? t("מחובר", "Connected")
          : source.state === "expired" ? t("נדרש אישור מחדש", "Reauthorize")
            : t("לא מחובר", "Disconnected");
  return <span className="provider"><span className="provider-initial">{name[0]}</span>
    <span><bdi>{name}</bdi><small>{label}</small></span>
  </span>;
}
