export interface EmployeeFlag {
  key: string;
  label: string;
  description?: string;
  value: boolean;
  can_edit: boolean;
}

export interface PatternDay {
  label: string; // "Monday"
  start: string | null; // "HH:MM"
  end: string | null;
}

export interface PatternSummary {
  effective_from: string;
  through: string | null;
  cycle_weeks: number;
  current_cycle_label: string | null;
  weeks: { label: string; days: PatternDay[] }[];
}

export interface EmployeeDetail {
  id: string;
  email: string;
  start_date: string;
  last_day: string | null;
  flags: EmployeeFlag[];
  pattern: PatternSummary | null;
  can: { send_welcome: boolean };
}
