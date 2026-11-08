"use client";

import { useId } from 'react';
import type { Settings, Translate } from '@/lib/types';

type Kind = 'unchanged' | 'added' | 'changed' | 'missing';
type Field = 'name' | 'instructor';
type RosterRow = {
  kind: Kind; code: string; name: string;
  local_name: string | null; source_name: string | null;
  local_instructor: string | null; source_instructor: string | null;
  fields: Field[]; missing_fields: Field[];
};
export type RosterPreview = {
  fixture: true; status: 'ready' | 'needs_review' | 'login_required'; reason: string | null;
  observed_at?: string | null; rows?: RosterRow[]; counts?: Record<Kind, number>;
};

const reasons: Record<string, [string, string]> = {
  login_required: ['נדרשת התחברות. המידע הקודם נשמר.', 'Sign-in required. Existing information is retained.'],
  source_timeout: ['המקור לא הגיב בזמן. המידע הקודם נשמר.', 'The source did not respond in time. Existing information is retained.'],
  incomplete_source: ['הדוח אינו מלא. הקורסים הקיימים נשמרים.', 'The report is incomplete. Existing courses are retained.'],
  unsupported_semester: ['הסמסטר הזה עדיין אינו נתמך בייבוא.', 'This semester is not yet supported for import.'],
  missing_term_dates: ['תאריכי הסמסטר לא סופקו במקור.', 'Term dates were not provided by the source.'],
  term_mismatch: ['תאריכי הסמסטר שונים ודורשים בדיקה.', 'Term dates differ and need review.'],
  unknown_term: ['הסמסטר עדיין אינו מוכר באתר.', 'This term is not yet known to the app.'],
  account_mismatch: ['זהות החשבון אינה תואמת. ההשוואה נעצרה.', 'Account identity differs. Comparison stopped.'],
  manual_course_conflict: ['קוד קורס מתנגש בקורס מקומי. נדרשת בדיקה.', 'A source code conflicts with a local course. Review is required.'],
  ambiguous_local_codes: ['קוד קורס מופיע יותר מפעם אחת באתר. נדרשת בדיקה.', 'A course code occurs more than once locally. Review is required.'],
};

/** Fixture-only component; deliberately not mounted in the personal application. */
export function BraudeRosterPreview({preview, settings, t}: {
  preview: RosterPreview; settings: Pick<Settings, 'language' | 'timezone'>; t: Translate;
}) {
  const heading = useId();
  if (preview.fixture !== true) return null;
  const counts = preview.counts ?? {unchanged:0, added:0, changed:0, missing:0};
  const differences = counts.added + counts.changed + counts.missing;
  const rows = (preview.rows ?? []).filter(row => row.kind !== 'unchanged' || row.missing_fields.length);
  const state = reasons[preview.reason ?? ''] ?? ['לא ניתן להשלים את ההשוואה. המידע הקודם נשמר.', 'Comparison could not complete. Existing information is retained.'];
  const observed = preview.observed_at ? new Date(preview.observed_at) : null;
  const labels: Record<Kind, string> = {
    added:t('חדש במקור', 'New in source'), changed:t('פרטים שונים', 'Details differ'),
    missing:t('לא נמצא בדוח — הקורס נשמר', 'Not in this report · course retained'),
    unchanged:t('ללא שינוי בפרטים שסופקו', 'Provided details unchanged'),
  };
  return <section className="google-settings" aria-labelledby={heading} dir={settings.language === 'he' ? 'rtl' : 'ltr'}>
    <h3 id={heading}>{t('בדיקת רשימת הקורסים', 'Course roster preview')}</h3>
    <p className="field-help">{t('דמה בלבד · ללא חיבור למכללה', 'Fixture only · not connected to the college')}</p>
    {observed && Number.isFinite(observed.getTime()) && <p className="record-meta"><time dateTime={preview.observed_at!}>{new Intl.DateTimeFormat(settings.language, {dateStyle:'short', timeStyle:'short', timeZone:settings.timezone}).format(observed)}</time></p>}
    {preview.status !== 'ready' ? <p role="status">{t(...state)}</p> : <>
      <p role="status">{t(`${differences} הבדלים · ${counts.unchanged} ללא שינוי`, `${differences} differences · ${counts.unchanged} unchanged`)}</p>
      {!!rows.length && <details className="item-extra"><summary>{t('פירוט ההבדלים', 'Review differences')}</summary>
        <ul className="academic-list">{rows.map(row => <li key={row.code}><div className="academic-record-content">
          <strong dir="auto">{row.name}</strong> <bdi>{row.code}</bdi>
          <p className="record-meta">{labels[row.kind]}</p>
          {row.fields.map(field => <div key={field}>
            <p>{field === 'name' ? t('שם באתר', 'Local name') : t('מרצה באתר', 'Local instructor')}: <bdi>{row[`local_${field}`]}</bdi></p>
            <p>{field === 'name' ? t('שם במקור', 'Source name') : t('מרצה במקור', 'Source instructor')}: <bdi>{row[`source_${field}`]}</bdi></p>
          </div>)}
          {row.missing_fields.includes('instructor') && <p className="field-help">{t('מרצה לא סופק במקור', 'Instructor not provided by source')}</p>}
        </div></li>)}</ul>
      </details>}
      <p className="field-help">{t('זו בדיקת הבדלים בלבד; לא שונה מידע.', 'Comparison only; no information has been changed.')}</p>
    </>}
  </section>;
}
