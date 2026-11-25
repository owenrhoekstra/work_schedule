import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";

// Mutable state that mock useOverrideMutation delegates to. Refs are
// created in beforeEach (real Vue refs, so computed/template track
// them). The mock factory returns the *current* value at setup time,
// which is always after beforeEach has run.
const { mockState } = vi.hoisted(() => ({
  mockState: {
    isPending: null as unknown as { value: boolean },
    error: null as unknown as { value: Error | null },
    mutate: null as unknown as (...args: unknown[]) => void,
    reset: null as unknown as () => void,
  },
}));

vi.mock("@/queries/overrides", () => ({
  useOverrideMutation: () => ({
    isPending: mockState.isPending,
    error: mockState.error,
    mutate: mockState.mutate,
    reset: mockState.reset,
  }),
}));

// Popover primitives are mocked to render inline (no portal). The mock
// forces `open=true` on mount so the content is visible for testing
// without simulating a trigger click — the trigger's open/close is a
// reka-ui concern, not ours.
vi.mock("@/components/ui/popover", () => ({
  Popover: {
    name: "Popover",
    props: { open: Boolean },
    emits: ["update:open"],
    template: "<div><slot /></div>",
    mounted(this: { $emit: (e: string, v: boolean) => void }) {
      this.$emit("update:open", true);
    },
  },
  PopoverTrigger: {
    name: "PopoverTrigger",
    template: '<div data-testid="popover-trigger"><slot /></div>',
  },
  PopoverContent: {
    name: "PopoverContent",
    template: '<div data-testid="popover-content"><slot /></div>',
  },
}));

import OverridePopover from "@/components/Schedule/OverridePopover.vue";
import type { Cell } from "@/types/Schedule/week.ts";

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

// Track the mounted wrapper so afterEach can unmount it. Mounting with
// attachTo puts the component in the real document, which jsdom needs
// in order to submit a <form> when its submit button is clicked.
let wrapper: VueWrapper | undefined;

function mountPopover(props: Record<string, unknown> = {}) {
  wrapper = mount(OverridePopover, {
    attachTo: document.body,
    props: {
      employeeId: "e1",
      employeeName: "Ada Lovelace",
      cell: makeCell(),
      dayLabel: "Monday",
      dateLabel: "Nov 16",
      canAddShift: true,
      canDeleteShift: true,
      editable: true,
      ...props,
    },
  });
  return wrapper;
}

beforeEach(() => {
  mockState.isPending = ref(false);
  mockState.error = ref<Error | null>(null);
  mockState.mutate = vi.fn();
  mockState.reset = vi.fn();
});

afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
});

describe("OverridePopover", () => {
  it("renders a plain span trigger when not editable", async () => {
    const wrapper = mountPopover({ editable: false });
    await nextTick();
    await nextTick();
    const trigger = wrapper.get('[data-testid="popover-trigger"]');
    expect(trigger.find("button").exists()).toBe(false);
    expect(trigger.find("span").exists()).toBe(true);
  });

  it("renders a button trigger when editable", async () => {
    const wrapper = mountPopover();
    await nextTick();
    await nextTick();
    expect(wrapper.get('[data-testid="popover-trigger"]').find("button").exists()).toBe(true);
  });

  it("pre-fills start and end from the cell", async () => {
    const wrapper = mountPopover();
    await nextTick();
    await nextTick();
    const inputs = wrapper.findAll('input[type="text"]');
    expect((inputs[0]!.element as HTMLInputElement).value).toBe("9:00 AM");
    expect((inputs[1]!.element as HTMLInputElement).value).toBe("5:00 PM");
  });

  it("pre-fills from defaults when the cell has no override", async () => {
    const wrapper = mountPopover({
      cell: makeCell({ kind: "none", start: null, end: null }),
    });
    await flushPromises();
    await nextTick();
    const inputs = wrapper.findAll('input[type="text"]');
    expect((inputs[0]!.element as HTMLInputElement).value).toBe("9:00 AM");
    expect((inputs[1]!.element as HTMLInputElement).value).toBe("5:00 PM");
  });

  it("hides Save when canAddShift is false", async () => {
    const wrapper = mountPopover({ canAddShift: false });
    await nextTick();
    await nextTick();
    expect(wrapper.findAll("button").some((b) => b.text() === "Save")).toBe(false);
  });

  it("hides Mark off when canDeleteShift is false", async () => {
    const wrapper = mountPopover({ canDeleteShift: false });
    await nextTick();
    await nextTick();
    expect(wrapper.findAll("button").some((b) => b.text() === "Mark off")).toBe(false);
  });

  it("hides Reset when the cell has no override", async () => {
    const wrapper = mountPopover();
    await nextTick();
    await nextTick();
    expect(wrapper.findAll("button").some((b) => b.text() === "Reset")).toBe(false);
  });

  it("shows Reset when the cell has an override", async () => {
    const wrapper = mountPopover({
      cell: makeCell({ kind: "override", has_override: true }),
    });
    await nextTick();
    await nextTick();
    expect(wrapper.findAll("button").some((b) => b.text() === "Reset")).toBe(true);
  });

  it("disables Save when either time field is empty", async () => {
    const wrapper = mountPopover();
    await nextTick();
    await nextTick();
    const inputs = wrapper.findAll('input[type="text"]');
    await inputs[0]!.setValue("");
    await nextTick();
    const saveBtn = wrapper.findAll("button").find((b) => b.text() === "Save");
    expect(saveBtn!.attributes("disabled")).toBeDefined();
  });

  it("calls mutate with action=save and the typed times", async () => {
    const wrapper = mountPopover();
    await nextTick();
    await nextTick();
    const saveBtn = wrapper.findAll("button").find((b) => b.text() === "Save");
    await saveBtn!.trigger("click");
    await flushPromises();
    expect(mockState.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        employeeId: "e1",
        date: "2026-11-16",
        action: "save",
        start: "9:00 AM",
        end: "5:00 PM",
        notify: false,
      }),
      expect.any(Object),
    );
  });

  it("calls mutate with action=off on Mark off", async () => {
    const wrapper = mountPopover();
    await nextTick();
    await nextTick();
    const btn = wrapper.findAll("button").find((b) => b.text() === "Mark off");
    await btn!.trigger("click");
    expect(mockState.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        employeeId: "e1",
        date: "2026-11-16",
        action: "off",
      }),
      expect.any(Object),
    );
  });

  it("calls mutate with action=reset on Reset", async () => {
    const wrapper = mountPopover({
      cell: makeCell({ kind: "override", has_override: true }),
    });
    await nextTick();
    await nextTick();
    const btn = wrapper.findAll("button").find((b) => b.text() === "Reset");
    await btn!.trigger("click");
    expect(mockState.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        employeeId: "e1",
        date: "2026-11-16",
        action: "reset",
      }),
      expect.any(Object),
    );
  });

  it("displays the server error inline when mutation.error is set", async () => {
    mockState.error.value = new Error("End time must be after start time.");
    const wrapper = mountPopover();
    await nextTick();
    await nextTick();
    expect(wrapper.text()).toContain("End time must be after start time.");
  });

  it("disables action buttons while submitting", async () => {
    mockState.isPending.value = true;
    const wrapper = mountPopover();
    await nextTick();
    await nextTick();
    const disabled = wrapper
      .findAll("button")
      .filter((b) => b.attributes("disabled") !== undefined);
    expect(disabled.length).toBeGreaterThan(0);
  });
});
