// TypeScript mirror of schedule/api/schemas.py. Keep field names and
// nullable/optional shapes in sync — the API emits snake_case; do not
// camelCase the wire shape.

export type CellKind =
  "default" | "override" | "off_override" | "day_override" | "not_employed" | "none";

export interface Cell {
  date: string; // ISO date (YYYY-MM-DD)
  weekday: number; // 0=Mon … 5=Sat
  kind: CellKind;
  start: string | null; // "HH:MM" 24h, null when not scheduled
  end: string | null;
  has_override: boolean;
  is_employed: boolean;
  default_start: string | null; // "HH:MM" or null; pattern default for this day
  default_end: string | null;
}

export interface DayHeader {
  date: string;
  weekday: number;
  short_label: string; // "Mon"
  long_label: string; // "Monday"
  date_label: string; // "Nov 16"
  override_status: string | null; // "closed" | "holiday" | null
}

export interface CycleRef {
  label: string; // "A" | "B" | "C" | "D"
  offset: number; // 0-indexed position in the cycle
  total: number; // cycle_weeks (1–4)
}

export interface WeekEmployee {
  id: string;
  first_name: string;
  last_name: string;
  display_name: string;
  role_id: string | null;
  role_name: string | null;
  last_day: string | null;
  cycle: CycleRef | null;
  cells: Cell[]; // len 6 (Mon–Sat)
  total_minutes: number;
}

export interface WeekRef {
  start: string; // ISO Monday
  title: string; // "Week of November 16th"
  prev: string; // ISO Monday
  next: string; // ISO Monday
  is_current: boolean;
  can_go_back: boolean;
}

export interface ViewerCan {
  can_add_shift: boolean; // gates "Save"
  can_delete_shift: boolean; // gates "Mark off" / "Reset to default"
  set_day_override: boolean;
  add_employee: boolean;
  print: boolean;
}

export interface WeekResponse {
  week: WeekRef;
  days: DayHeader[]; // len 6
  scope: string; // "me" | "team" | "company"
  available_scopes: string[];
  employees: WeekEmployee[];
  viewer_can: ViewerCan;
}
