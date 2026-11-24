import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, nextTick } from "vue";

const { mockPost, mockToastError } = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockToastError: vi.fn(),
}));

vi.mock("@/composables/useApi", () => ({
  useApi: () => ({ post: mockPost }),
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      message: string,
    ) {
      super(message);
    }
    get isUnauthorized() {
      return this.status === 401;
    }
    get isForbidden() {
      return this.status === 403;
    }
  },
}));

vi.mock("vue-sonner", () => ({
  toast: { error: mockToastError, success: vi.fn() },
}));

import { useOverrideMutation } from "@/queries/overrides";
import type { Cell, WeekEmployee, WeekResponse } from "@/types/week";

function makeCell(overrides: Partial<Cell> = {}): Cell {
  return {
    date: "2026-11-16",
    weekday: 0,
    kind: "default",
    start: "09:00",
    end: "17:00",
    has_override: false,
    is_employed: true,
    default_start: "09:00",
    default_end: "17:00",
    ...overrides,
  };
}

function makeWeek(cells: Cell[] = [makeCell()]): WeekResponse {
  return {
    week: {
      start: "2026-11-16",
      title: "Week of Nov 16",
      prev: "",
      next: "",
      is_current: false,
      can_go_back: true,
    },
    days: Array.from({ length: 6 }, (_, i) => ({
      date: `2026-11-${16 + i}`,
      weekday: i,
      short_label: "",
      long_label: "",
      date_label: "",
      override_status: null,
    })),
    scope: "company",
    available_scopes: ["company"],
    employees: [
      {
        id: "e1",
        first_name: "Ada",
        last_name: "Lovelace",
        display_name: "Ada Lovelace",
        role_id: null,
        role_name: null,
        last_day: null,
        cycle: null,
        cells,
        total_minutes: 480,
      },
    ],
    viewer_can: {
      can_add_shift: true,
      can_delete_shift: true,
      change_employee_day_override: true,
      change_day_override: true,
      add_employee: true,
      print: true,
    },
  };
}

const TestHarness = defineComponent({
  setup(_, { expose }) {
    expose({ mutation: useOverrideMutation() });
    return () => null;
  },
});

function makeDeferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

let queryClient: QueryClient;

beforeEach(() => {
  mockPost.mockReset();
  mockToastError.mockReset();
  queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
});

async function mountMutation() {
  const wrapper = mount(TestHarness, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  });
  await nextTick();
  return (
    wrapper.vm as unknown as {
      mutation: ReturnType<typeof useOverrideMutation>;
    }
  ).mutation;
}

describe("useOverrideMutation", () => {
  it("optimistically applies save, then replaces with the server row", async () => {
    const fixture = makeWeek();
    queryClient.setQueryData(["week", null, "company"], fixture);

    const deferred = makeDeferred<{
      employee: WeekEmployee;
      notification_sent: boolean;
      notification_error: string | null;
    }>();
    mockPost.mockReturnValueOnce(deferred.promise);

    const mutation = await mountMutation();
    const promise = mutation.mutateAsync({
      employeeId: "e1",
      date: "2026-11-16",
      action: "save",
      start: "10:00",
      end: "18:00",
    });

    await vi.waitFor(() => {
      const during = queryClient.getQueryData<WeekResponse>(["week", null, "company"]);
      const cell = during?.employees[0]?.cells[0];
      expect(cell?.start).toBe("10:00");
      expect(cell?.end).toBe("18:00");
      expect(cell?.kind).toBe("override");
      expect(cell?.has_override).toBe(true);
    });

    const serverRow: WeekEmployee = {
      ...fixture.employees[0]!,
      cells: [
        makeCell({
          kind: "override",
          start: "10:00",
          end: "18:00",
          has_override: true,
        }),
        ...fixture.employees[0]!.cells.slice(1),
      ],
      total_minutes: 480,
    };
    deferred.resolve({
      employee: serverRow,
      notification_sent: false,
      notification_error: null,
    });
    await promise;

    const after = queryClient.getQueryData<WeekResponse>(["week", null, "company"]);
    expect(after?.employees[0]?.cells[0]?.start).toBe("10:00");
  });

  it("rolls back the optimistic update when the request fails", async () => {
    const fixture = makeWeek();
    queryClient.setQueryData(["week", null, "company"], fixture);

    const deferred = makeDeferred<unknown>();
    mockPost.mockReturnValueOnce(deferred.promise);

    const mutation = await mountMutation();
    const promise = mutation.mutateAsync({
      employeeId: "e1",
      date: "2026-11-16",
      action: "save",
      start: "10:00",
      end: "18:00",
    });

    await vi.waitFor(() => {
      const during = queryClient.getQueryData<WeekResponse>(["week", null, "company"]);
      expect(during?.employees[0]?.cells[0]?.start).toBe("10:00");
    });

    deferred.reject(new Error("Server error"));
    await expect(promise).rejects.toThrow("Server error");

    await vi.waitFor(() => {
      const after = queryClient.getQueryData<WeekResponse>(["week", null, "company"]);
      expect(after?.employees[0]?.cells[0]?.start).toBe("09:00");
      expect(after?.employees[0]?.cells[0]?.kind).toBe("default");
    });
  });

  it("reset restores default_start / default_end optimistically", async () => {
    const fixture = makeWeek([
      makeCell({
        kind: "override",
        start: "10:00",
        end: "18:00",
        has_override: true,
      }),
    ]);
    queryClient.setQueryData(["week", null, "company"], fixture);

    const deferred = makeDeferred<unknown>();
    mockPost.mockReturnValueOnce(deferred.promise);

    const mutation = await mountMutation();
    const promise = mutation.mutateAsync({
      employeeId: "e1",
      date: "2026-11-16",
      action: "reset",
    });

    await vi.waitFor(() => {
      const during = queryClient.getQueryData<WeekResponse>(["week", null, "company"]);
      const cell = during?.employees[0]?.cells[0];
      expect(cell?.kind).toBe("default");
      expect(cell?.start).toBe("09:00");
      expect(cell?.end).toBe("17:00");
      expect(cell?.has_override).toBe(false);
    });

    deferred.resolve({
      employee: fixture.employees[0]!,
      notification_sent: false,
      notification_error: null,
    });
    await promise;
  });

  it("reset with no pattern default produces kind=none", async () => {
    const fixture = makeWeek([
      makeCell({
        kind: "override",
        start: "10:00",
        end: "18:00",
        has_override: true,
        default_start: null,
        default_end: null,
      }),
    ]);
    queryClient.setQueryData(["week", null, "company"], fixture);

    const deferred = makeDeferred<unknown>();
    mockPost.mockReturnValueOnce(deferred.promise);

    const mutation = await mountMutation();
    const promise = mutation.mutateAsync({
      employeeId: "e1",
      date: "2026-11-16",
      action: "reset",
    });

    await vi.waitFor(() => {
      const during = queryClient.getQueryData<WeekResponse>(["week", null, "company"]);
      const cell = during?.employees[0]?.cells[0];
      expect(cell?.kind).toBe("none");
      expect(cell?.start).toBeNull();
      expect(cell?.end).toBeNull();
      expect(cell?.has_override).toBe(false);
    });

    deferred.resolve({
      employee: fixture.employees[0]!,
      notification_sent: false,
      notification_error: null,
    });
    await promise;
  });

  it("off sets kind=off_override optimistically", async () => {
    const fixture = makeWeek();
    queryClient.setQueryData(["week", null, "company"], fixture);

    const deferred = makeDeferred<unknown>();
    mockPost.mockReturnValueOnce(deferred.promise);

    const mutation = await mountMutation();
    const promise = mutation.mutateAsync({
      employeeId: "e1",
      date: "2026-11-16",
      action: "off",
    });

    await vi.waitFor(() => {
      const during = queryClient.getQueryData<WeekResponse>(["week", null, "company"]);
      const cell = during?.employees[0]?.cells[0];
      expect(cell?.kind).toBe("off_override");
      expect(cell?.start).toBeNull();
      expect(cell?.end).toBeNull();
      expect(cell?.has_override).toBe(true);
    });

    deferred.resolve({
      employee: fixture.employees[0]!,
      notification_sent: false,
      notification_error: null,
    });
    await promise;
  });

  it("adjusts total_minutes optimistically", async () => {
    const fixture = makeWeek(); // 09:00–17:00 = 480 min
    queryClient.setQueryData(["week", null, "company"], fixture);

    const deferred = makeDeferred<unknown>();
    mockPost.mockReturnValueOnce(deferred.promise);

    const mutation = await mountMutation();
    const promise = mutation.mutateAsync({
      employeeId: "e1",
      date: "2026-11-16",
      action: "save",
      start: "08:00",
      end: "18:00",
    });

    await vi.waitFor(() => {
      const during = queryClient.getQueryData<WeekResponse>(["week", null, "company"]);
      // 08:00–18:00 = 600 min, replacing 480 → total 600.
      expect(during?.employees[0]?.total_minutes).toBe(600);
    });

    deferred.resolve({
      employee: fixture.employees[0]!,
      notification_sent: false,
      notification_error: null,
    });
    await promise;
  });

  it("toasts notification failure on successful save with notify=true", async () => {
    const fixture = makeWeek();
    queryClient.setQueryData(["week", null, "company"], fixture);

    const deferred = makeDeferred<{
      employee: WeekEmployee;
      notification_sent: boolean;
      notification_error: string | null;
    }>();
    mockPost.mockReturnValueOnce(deferred.promise);

    const mutation = await mountMutation();
    const promise = mutation.mutateAsync({
      employeeId: "e1",
      date: "2026-11-16",
      action: "save",
      start: "10:00",
      end: "18:00",
      notify: true,
    });

    deferred.resolve({
      employee: fixture.employees[0]!,
      notification_sent: false,
      notification_error: "SMTP down",
    });
    await promise;

    expect(mockToastError).toHaveBeenCalledWith("Notification not sent: SMTP down");
  });

  it("does not toast when notify is false", async () => {
    const fixture = makeWeek();
    queryClient.setQueryData(["week", null, "company"], fixture);

    const deferred = makeDeferred<unknown>();
    mockPost.mockReturnValueOnce(deferred.promise);

    const mutation = await mountMutation();
    const promise = mutation.mutateAsync({
      employeeId: "e1",
      date: "2026-11-16",
      action: "save",
      start: "10:00",
      end: "18:00",
      notify: false,
    });

    deferred.resolve({
      employee: fixture.employees[0]!,
      notification_sent: false,
      notification_error: "SMTP down", // still failed, but caller opted out
    });
    await promise;

    expect(mockToastError).not.toHaveBeenCalled();
  });
});
