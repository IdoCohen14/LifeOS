export type GoogleCalendarStatus = {
  configured: boolean;
  connected: boolean;
  state: string;
  error: string | null;
  last_success: number | null;
  next_sync: number | null;
  syncing: boolean;
  stale: boolean;
  calendars: {
    id: string;
    name: string;
    timezone: string;
    selected: boolean;
  }[];
  window_days: { past: number; future: number };
};
