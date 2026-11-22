import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { toast } from "vue-sonner";
import { useApi } from "@/composables/useApi";
import type { Cell, OverrideResponse, WeekEmployee, WeekResponse } from "@/types/week";

// Wire shape mirrors schedule/api/schemas.py's OverrideRequest.
// `start` / `end` are user-entered strings; the server's _parse_time
// accepts "HH:MM", "9:00 AM", "0900", etc. We optimistically apply
// what the user typed — if the server normalizes to "HH:MM", the
// onSuccess replacement corrects the cell.
export interface OverrideVars {
  employeeId: string;
  date: string; // "YYYY-MM-DD"
  action: "save" | "off" | "reset";
  start?: string;
  end?: string;
  notify?: boolean;
}

// Best-effort client parse mirror of the server's _parse_time (subset
// — enough to build an optimistic cell). Returns "HH:MM" or null.
function parseToHHMM(raw: string | undefined): string | null {
  if (!raw) return null;
  const s = raw.trim().replace(/\./g, ":").toUpperCase();
  // "HH:MM" / "H:MM" / "HH:MM:SS"
  let m = s.match(/^(\d{1,2}):(\d{2})(?::\d{2})?\s*(AM|PM)?$/);
  if (m) {
    let h = parseInt(m[1]!, 10);
    const min = parseInt(m[2]!, 10);
    if (m[3] === "AM") h = h === 12 ? 0 : h;
    else if (m[3] === "PM") h = h === 12 ? h : h + 12;
    if (h < 0 || h > 23 || min < 0 || min > 59) return null;
    return `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
  }
  // "HHMM"
  m = s.match(/^(\d{4})$/);
  if (m) {
    const h = parseInt(m[1]!.slice(0, 2), 10);
    const min = parseInt(m[1]!.slice(2), 10);
    if (h < 0 || h > 23 || min < 0 || min > 59) return null;
    return `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
  }
  // "H AM" / "H PM"
  m = s.match(/^(\d{1,2})\s*(AM|PM)$/);
  if (m) {
    let h = parseInt(m[1]!, 10);
    if (m[2] === "AM") h = h === 12 ? 0 : h;
    else h = h === 12 ? h : h + 12;
    if (h < 0 || h > 23) return null;
    return `${String(h).padStart(2, "0")}:00`;
  }
  return null;
}

function cellMinutes(cell: Cell): number {
  if (!cell.start || !cell.end) return 0;
  const [sh, sm] = cell.start.split(":").map(Number);
  const [eh, em] = cell.end.split(":").map(Number);
  return eh! * 60 + em! - (sh! * 60 + sm!);
}

// Build the optimistic cell the client shows before the server responds.
// Mirrors the server's cell construction in selectors._build_cell.
// Returns the unchanged cell if we can't construct a plausible one
// (parse failure on save) — the server will reject and rollback.
function optimisticCell(current: Cell, vars: OverrideVars): Cell {
  if (vars.action === "off") {
    return { ...current, kind: "off_override", start: null, end: null, has_override: true };
  }
  if (vars.action === "reset") {
    if (current.default_start && current.default_end) {
      return {
        ...current,
        kind: "default",
        start: current.default_start,
        end: current.default_end,
        has_override: false,
      };
    }
    return { ...current, kind: "none", start: null, end: null, has_override: false };
  }
  // save — parse both; if either fails, return unchanged so we don't
  // lie about what the server will do (422 will surface inline).
  const start = parseToHHMM(vars.start);
  const end = parseToHHMM(vars.end);
  if (!start || !end) return current;
  return { ...current, kind: "override", start, end, has_override: true };
}

function patchEmployee(
  old: WeekResponse,
  employeeId: string,
  date: string,
  makeCell: (current: Cell) => Cell,
): WeekResponse {
  const emp = old.employees.find((e) => e.id === employeeId);
  if (!emp) return old;
  const idx = emp.cells.findIndex((c) => c.date === date);
  if (idx === -1) return old;
  const currentCell = emp.cells[idx]!;
  const nextCell = makeCell(currentCell);
  if (nextCell === currentCell) return old;
  const nextCells = emp.cells.slice();
  nextCells[idx] = nextCell;
  const nextEmp: WeekEmployee = {
    ...emp,
    cells: nextCells,
    total_minutes: emp.total_minutes - cellMinutes(currentCell) + cellMinutes(nextCell),
  };
  return {
    ...old,
    employees: old.employees.map((e) => (e.id === employeeId ? nextEmp : e)),
  };
}

function replaceEmployee(old: WeekResponse, fresh: WeekEmployee): WeekResponse {
  if (!old.employees.some((e) => e.id === fresh.id)) return old;
  return {
    ...old,
    employees: old.employees.map((e) => (e.id === fresh.id ? fresh : e)),
  };
}

export function useOverrideMutation() {
  const api = useApi();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (vars: OverrideVars) =>
      api.post<OverrideResponse>(`/schedule/overrides/${vars.employeeId}/${vars.date}/`, {
        action: vars.action,
        start: vars.start ?? null,
        end: vars.end ?? null,
        notify: vars.notify ?? false,
      }),

    // Optimistic update: patch every cached week that contains this
    // employee. setQueriesData applies the updater to all matching
    // ["week", ...] caches (one per scope), so the row stays correct
    // if the user switches scopes mid-save. Non-matching weeks (where
    // the employee isn't in the roster) return unchanged.
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: ["week"] });
      const previous = queryClient.getQueriesData<WeekResponse>({ queryKey: ["week"] });
      queryClient.setQueriesData<WeekResponse>({ queryKey: ["week"] }, (old) =>
        old ? patchEmployee(old, vars.employeeId, vars.date, (c) => optimisticCell(c, vars)) : old,
      );
      return { previous };
    },

    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) {
        for (const [key, data] of ctx.previous) {
          queryClient.setQueryData(key, data);
        }
      }
    },

    // Success: replace the optimistic cell with the server's
    // authoritative row (also corrects total_minutes and any
    // normalization of "HH:MM"). Then surface a toast if the save
    // succeeded but the notification email failed — the cell change
    // is real; only the email is broken.
    onSuccess: (data, vars) => {
      queryClient.setQueriesData<WeekResponse>({ queryKey: ["week"] }, (old) =>
        old ? replaceEmployee(old, data.employee) : old,
      );
      if (vars.notify && !data.notification_sent && data.notification_error) {
        toast.error(`Notification not sent: ${data.notification_error}`);
      }
    },
  });
}
