export type TrackedRequest = {
  id: string; title: string; course_name: string; due: string | null;
  status: "waiting_user" | "waiting_approval" | "waiting_source" | "done";
  version: number; created_at: string; updated_at: string; followup_at: number | null;
  resume_proposal?: { id: string; kind: "task" | "event"; payload: { title: string; due?: string; start?: string; end?: string }; change_from?: {start:string;end:string} };
};
export type AssistantChatHandle = { openRequest: (item: TrackedRequest) => boolean };
