"use client";
import { useRef, useState, type FormEvent } from "react";
import { Download, FileSearch, FileText, Trash2, Upload } from "lucide-react";
import { api } from "@/lib/api";
import {
  sourceReference,
  type DocumentSection,
  type SearchHit,
  type StudyDocument,
} from "@/lib/academic";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

export function CourseDocuments({
  courseId,
  documents,
  csrf,
  settings,
  t,
  onChanged,
  onUnauthorized,
}: {
  courseId: string;
  documents: StudyDocument[];
  csrf: string;
  settings: Settings;
  t: Translate;
  onChanged: () => Promise<void>;
  onUnauthorized: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [preview, setPreview] = useState<
    (StudyDocument & { sections: DocumentSection[] }) | null
  >(null);
  const [deleting, setDeleting] = useState<StudyDocument | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  function failure(error: unknown) {
    if (error instanceof Error && "status" in error && error.status === 429) {
      setError(t(
        "עיבוד קבצים אחרים עדיין מתבצע. המתינו מעט ונסו להעלות שוב; הקובץ שבחרתם נשאר בטופס.",
        "Other files are still processing. Wait briefly and retry; your selected file remains in the form.",
      ));
      return;
    }
    if (error instanceof Error && "status" in error && error.status === 401)
      onUnauthorized();
    setError(
      t(
        "הפעולה נכשלה. בדקו את החיבור, סוג הקובץ ומגבלת 8 MiB. קובץ סרוק דורש OCR שאינו זמין עדיין.",
        "Operation failed. Check connection, format and 8 MiB limit. Scanned files need OCR, which is not available yet.",
      ),
    );
  }
  async function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) {
      setError(t("הקובץ גדול מ־8 MiB.", "File exceeds 8 MiB."));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const encoded = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
      await api(
        "academic/documents",
        "POST",
        { course_id: courseId, filename: file.name, content_base64: encoded },
        csrf,
      );
      await onChanged();
      if (fileRef.current) fileRef.current.value = "";
      setHits(null);
    } catch (error) {
      failure(error);
    } finally {
      setBusy(false);
    }
  }
  async function search(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = String(new FormData(e.currentTarget).get("q") ?? "").trim();
    if (!q) {
      setHits(null);
      return;
    }
    setBusy(true);
    setError("");
    try {
      setHits(
        await api<SearchHit[]>(
          `academic/documents/search?q=${encodeURIComponent(q)}&course_id=${courseId}`,
        ),
      );
    } catch (error) {
      failure(error);
    } finally {
      setBusy(false);
    }
  }
  async function view(id: string) {
    setBusy(true);
    try {
      setPreview(await api(`academic/documents/${id}`));
    } catch (error) {
      failure(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="document-workspace">
      <form className="upload-box" onSubmit={upload}>
        <Upload size={23} aria-hidden="true" />
        <div>
          <h3>{t("חומרי הלימוד שלך", "Your study materials")}</h3>
          <p className="field-help">
            PDF, DOCX, PPTX, TXT, Markdown ·{" "}
            {t(
              "עד 8 MiB לקובץ · חיפוש מקומי, ללא AI",
              "Up to 8 MiB each · Local search, no AI",
            )}
          </p>
        </div>
        <label className="upload-input">
          {t("בחירת קובץ", "Choose file")}
          <input
            ref={fileRef}
            type="file"
            required
            accept=".pdf,.docx,.pptx,.txt,.md"
          />
        </label>
        <Button type="submit" disabled={busy}>
          {busy ? t("מעבד…", "Processing…") : t("העלאה", "Upload")}
        </Button>
      </form>
      <form className="document-search" onSubmit={search}>
        <label className="sr-only" htmlFor="course-search">
          {t("חיפוש בקבצים", "Search course files")}
        </label>
        <input
          id="course-search"
          name="q"
          type="search"
          maxLength={160}
          placeholder={t(
            "חיפוש בחומרי הקורס…",
            "Search your course materials…",
          )}
        />
        <Button variant="secondary" type="submit" disabled={busy}>
          <FileSearch size={17} aria-hidden="true" />
          {t("חיפוש", "Search")}
        </Button>
      </form>
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      {hits !== null && (
        <section className="search-results" aria-live="polite">
          <div className="panel-heading">
            <h3>
              {t("תוצאות חיפוש", "Search results")} ({hits.length})
            </h3>
            <Button variant="ghost" onClick={() => setHits(null)}>
              {t("איפוס", "Clear")}
            </Button>
          </div>
          {hits.length === 0 ? (
            <p className="muted">
              {t(
                "לא נמצאו התאמות בטקסט שחולץ.",
                "No matches in extracted text.",
              )}
            </p>
          ) : (
            hits.map((hit, i) => (
              <button
                className="search-result"
                key={`${hit.document_id}-${i}`}
                onClick={() => view(hit.document_id)}
              >
                <strong dir="auto">{hit.filename}</strong>
                <span className="subtle-badge">
                  {sourceReference(hit.reference, settings.language === "he")}
                </span>
                <p dir="auto">{hit.excerpt}</p>
              </button>
            ))
          )}
        </section>
      )}
      <ul className="academic-list">
        {documents.map((document) => (
          <li key={document.id}>
            <FileText size={21} aria-hidden="true" />
            <div className="academic-record-content">
              <button
                className="text-button record-title"
                onClick={() => view(document.id)}
                dir="auto"
              >
                {document.filename}
              </button>
              <p className="record-meta">
                {new Intl.NumberFormat(settings.language, {
                  maximumFractionDigits: 1,
                }).format(document.size / 1024)}{" "}
                KiB ·{" "}
                {document.text_status === "no_text"
                  ? t("ללא טקסט ניתן לחיפוש", "No searchable text")
                  : document.text_status === "truncated"
                    ? t("אינדקס טקסט חלקי", "Partially indexed")
                    : t("זמין לחיפוש", "Searchable")}
              </p>
            </div>
            <a
              className="button button-ghost button-icon"
              href={`/api/academic/documents/${document.id}/download`}
              aria-label={`${t("הורדה", "Download")}: ${document.filename}`}
            >
              <Download size={17} aria-hidden="true" />
            </a>
            <Button
              variant="ghost"
              size="icon"
              disabled={busy}
              aria-label={`${t("מחיקה", "Delete")}: ${document.filename}`}
              onClick={() => setDeleting(document)}
            >
              <Trash2 size={17} aria-hidden="true" />
            </Button>
          </li>
        ))}
      </ul>
      {documents.length === 0 && (
        <p className="academic-empty">
          {t(
            "עדיין אין קבצים בקורס. אפשר להעלות סיכום או מצגת כדי להתחיל.",
            "No course files yet. Upload notes or slides to get started.",
          )}
        </p>
      )}
      {preview && (
        <Modal
          open
          onClose={() => setPreview(null)}
          title={preview.filename}
          description={t(
            "טקסט שחולץ מקומית. פריסת המסמך המקורי אינה מוצגת.",
            "Locally extracted text. Original document layout is not shown.",
          )}
          closeLabel={t("סגירה", "Close")}
        >
          <div className="document-preview">
            {preview.sections.map((section, i) => (
              <section key={i}>
                <h3>
                  {sourceReference(
                    section.reference,
                    settings.language === "he",
                  )}
                </h3>
                <p dir="auto">{section.text}</p>
              </section>
            ))}
            {!preview.sections.length && (
              <p className="muted">
                {t(
                  "אין טקסט שניתן לחלץ. ייתכן שזהו מסמך סרוק.",
                  "No extractable text. This may be a scanned document.",
                )}
              </p>
            )}
          </div>
        </Modal>
      )}
      {deleting && (
        <Modal
          open
          onClose={() => {
            if (!busy) setDeleting(null);
          }}
          title={t("למחוק את הקובץ?", "Delete this file?")}
          description={deleting.filename}
          closeLabel={t("סגירה", "Close")}
        >
          <p className="muted">
            {t(
              "הקובץ והטקסט שנוסף לחיפוש יימחקו לצמיתות.",
              "The file and its search index will be permanently removed.",
            )}
          </p>
          <div className="form-actions">
            <Button
              variant="danger"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await api(
                    `academic/documents/${deleting.id}`,
                    "DELETE",
                    undefined,
                    csrf,
                  );
                  setDeleting(null);
                  setHits(null);
                  await onChanged();
                } catch (error) {
                  failure(error);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {t("מחיקה", "Delete")}
            </Button>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => setDeleting(null)}
            >
              {t("ביטול", "Cancel")}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
