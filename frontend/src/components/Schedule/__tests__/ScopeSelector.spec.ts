import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ScopeSelector from "@/components/Schedule/ScopeSelector.vue";

describe("ScopeSelector", () => {
  it("renders nothing when no scopes are available", () => {
    const wrapper = mount(ScopeSelector, {
      props: { scopes: [], current: "me" },
    });
    expect(wrapper.find('[role="tablist"]').exists()).toBe(false);
    expect(wrapper.findAll('[role="tab"]')).toHaveLength(0);
  });

  it("renders nothing when only one scope is available", () => {
    const wrapper = mount(ScopeSelector, {
      props: { scopes: ["me"], current: "me" },
    });
    expect(wrapper.find('[role="tablist"]').exists()).toBe(false);
  });

  it("renders one tab per scope with friendly labels", () => {
    const wrapper = mount(ScopeSelector, {
      props: { scopes: ["me", "team", "company"], current: "company" },
    });

    const tabs = wrapper.findAll('[role="tab"]');
    expect(tabs).toHaveLength(3);
    expect(tabs[0]!.text()).toBe("Mine");
    expect(tabs[1]!.text()).toBe("Team");
    expect(tabs[2]!.text()).toBe("Company");
  });

  it("marks only the current scope as aria-selected=true", () => {
    const wrapper = mount(ScopeSelector, {
      props: { scopes: ["me", "team", "company"], current: "team" },
    });

    const tabs = wrapper.findAll('[role="tab"]');
    expect(tabs[0]!.attributes("aria-selected")).toBe("false");
    expect(tabs[1]!.attributes("aria-selected")).toBe("true");
    expect(tabs[2]!.attributes("aria-selected")).toBe("false");
  });

  it("emits select with the chosen scope on click", async () => {
    const wrapper = mount(ScopeSelector, {
      props: { scopes: ["me", "team", "company"], current: "me" },
    });

    const tabs = wrapper.findAll('[role="tab"]');
    await tabs[2]!.trigger("click");

    expect(wrapper.emitted("select")).toEqual([["company"]]);
  });

  it("falls back to the raw scope string for unknown values", () => {
    // If the server ever emits a scope we don't have a label for,
    // show the raw string instead of "undefined". Requires two scopes
    // to render (v-if hides the strip at length <= 1).
    const wrapper = mount(ScopeSelector, {
      props: { scopes: ["me", "custom"], current: "me" },
    });

    const tabs = wrapper.findAll('[role="tab"]');
    expect(tabs[0]!.text()).toBe("Mine");
    expect(tabs[1]!.text()).toBe("custom");
  });
});
