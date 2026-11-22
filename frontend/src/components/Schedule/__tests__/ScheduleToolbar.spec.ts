import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ScheduleToolbar from "@/components/Schedule/ScheduleToolbar.vue";
import type { ViewerCan, WeekRef } from "@/types/week";

function makeWeek(): WeekRef {
  return {
    start: "2026-11-16",
    title: "Week of November 16th",
    prev: "2026-11-09",
    next: "2026-11-23",
    is_current: false,
    can_go_back: true,
  };
}

function makeViewerCan(overrides: Partial<ViewerCan> = {}): ViewerCan {
  return {
    can_add_shift: true,
    can_delete_shift: true,
    set_day_override: true,
    add_employee: true,
    print: true,
    ...overrides,
  };
}

function mountToolbar(props: Record<string, unknown> = {}) {
  return mount(ScheduleToolbar, {
    props: {
      week: makeWeek(),
      scopes: ["me", "team", "company"],
      currentScope: "company",
      viewerCan: makeViewerCan(),
      ...props,
    },
  });
}

describe("ScheduleToolbar", () => {
  it("renders Print when viewerCan.print is true", () => {
    const wrapper = mountToolbar();
    expect(wrapper.text()).toContain("Print");
  });

  it("hides Print when viewerCan.print is false", () => {
    const wrapper = mountToolbar({ viewerCan: makeViewerCan({ print: false }) });
    expect(wrapper.text()).not.toContain("Print");
  });

  it("Print link points at /schedule/print/ with the current week", () => {
    const wrapper = mountToolbar();
    const link = wrapper.find('a[href*="/schedule/print/"]');
    expect(link.exists()).toBe(true);
    expect(link.attributes("href")).toBe("/schedule/print/?week=2026-11-16");
  });

  it("forwards navigate from WeekHeader", async () => {
    const wrapper = mountToolbar();
    await wrapper.find('button[aria-label="Next week"]').trigger("click");
    const emitted = wrapper.emitted("navigate");
    expect(emitted).toBeTruthy();
    expect(emitted![0]).toEqual(["2026-11-23"]);
  });

  it("forwards goCurrent from the back-to-current button", async () => {
    const wrapper = mountToolbar();
    const back = wrapper.findAll("button").find((b) => b.text() === "Back to current week");
    expect(back).toBeTruthy();
    await back!.trigger("click");
    expect(wrapper.emitted("goCurrent")).toBeTruthy();
  });

  it("forwards selectScope from ScopeSelector", async () => {
    const wrapper = mountToolbar();
    const tabs = wrapper.findAll('[role="tab"]');
    const mine = tabs.find((t) => t.text() === "Mine");
    await mine!.trigger("click");
    const emitted = wrapper.emitted("selectScope");
    expect(emitted).toBeTruthy();
    expect(emitted![0]).toEqual(["me"]);
  });

  it("does not render scope tabs for a single-scope viewer", () => {
    const wrapper = mountToolbar({ scopes: ["me"], currentScope: "me" });
    expect(wrapper.findAll('[role="tab"]')).toHaveLength(0);
  });
});
