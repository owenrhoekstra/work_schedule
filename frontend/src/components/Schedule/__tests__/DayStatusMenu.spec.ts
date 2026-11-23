// src/components/Schedule/__tests__/DayStatusMenu.spec.ts
import { mount } from "@vue/test-utils";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import DayStatusMenu from "../DayStatusMenu.vue";

const mutate = vi.fn();
vi.mock("@/queries/overrides", () => ({
  useDayOverrideMutation: () => ({ mutate, isPending: ref(false) }),
}));

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

const mountMenu = (props: { status: string | null; editable: boolean }) =>
  mount(DayStatusMenu, {
    props: { date: "2026-11-24", label: "Tuesday, Nov 24", ...props },
    slots: { default: "Tuesday" },
    attachTo: document.body,
  });

const menuText = () => document.body.textContent ?? "";
const clickItem = (text: string) =>
  [...document.body.querySelectorAll("button")].find((b) => b.textContent?.includes(text))!.click();

describe("DayStatusMenu", () => {
  it("renders a plain label with no button when not editable", () => {
    const w = mountMenu({ status: null, editable: false });
    expect(w.find("button").exists()).toBe(false);
    expect(w.text()).toContain("Tuesday");
  });

  it("makes the whole label a trigger when editable", () => {
    const w = mountMenu({ status: null, editable: true });
    expect(w.find("button").text()).toContain("Tuesday");
  });

  it("offers only valid actions for the current status", async () => {
    const w = mountMenu({ status: "closed", editable: true });
    await w.find("button").trigger("click");
    await vi.waitFor(() => expect(menuText()).toContain("Mark holiday"));
    expect(menuText()).not.toContain("Mark closed");
    expect(menuText()).toContain("Clear status");
  });

  it("calls the mutation with the chosen action", async () => {
    const w = mountMenu({ status: null, editable: true });
    await w.find("button").trigger("click");
    await vi.waitFor(() => expect(menuText()).toContain("Mark holiday"));
    clickItem("Mark holiday");
    expect(mutate).toHaveBeenCalledWith(
      { date: "2026-11-24", action: "holiday" },
      expect.any(Object),
    );
  });
});
