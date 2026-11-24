// WeekSelector.test.ts
import { mount } from "@vue/test-utils";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { WeekRef } from "@/types/week";
import WeekSelector from "../WeekSelector.vue";

// Week of Mon 2026-11-23
const week = { start: "2026-11-23", title: "Nov 23 – 29" } as WeekRef;

beforeAll(() => {
  // reka-ui popovers/calendars expect this; jsdom doesn't ship it.
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

afterEach(() => {
  document.body.innerHTML = "";
});

async function openPicker() {
  // PopoverContent portals to document.body, so attach and query there.
  const wrapper = mount(WeekSelector, {
    props: { week },
    slots: { default: "Pick week" },
    attachTo: document.body,
  });
  await wrapper.find("button").trigger("click");
  await wrapper.vm.$nextTick();
  return wrapper;
}

const day = (iso: string) => document.body.querySelector<HTMLElement>(`[data-value="${iso}"]`);

describe("WeekSelector", () => {
  it("renders the slot as the trigger label", () => {
    const wrapper = mount(WeekSelector, {
      props: { week },
      slots: { default: "Pick week" },
    });
    expect(wrapper.text()).toContain("Pick week");
  });

  it.each([
    ["midweek", "2026-11-25"],
    ["Sunday", "2026-11-29"],
  ])("snaps a %s click back to that week's Monday", async (_, iso) => {
    const wrapper = await openPicker();
    day(iso)!.click();
    expect(wrapper.emitted("navigate")![0]).toEqual(["2026-11-23"]);
  });

  it("emits the next Monday when a Monday of another week is clicked", async () => {
    const wrapper = await openPicker();
    day("2026-11-30")!.click();
    expect(wrapper.emitted("navigate")![0]).toEqual(["2026-11-30"]);
  });

  it("closes after selecting", async () => {
    const wrapper = await openPicker();
    day("2026-11-25")!.click();
    await vi.waitFor(() => expect(day("2026-11-25")).toBeNull());
    expect(wrapper.emitted("navigate")).toHaveLength(1);
  });
});
