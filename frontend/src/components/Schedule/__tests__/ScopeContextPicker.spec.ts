import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

const { mockSelectCompany, mockSelectTeam, mockMe } = vi.hoisted(() => ({
  mockSelectCompany: { mutate: null as unknown as (id: string) => void },
  mockSelectTeam: { mutate: null as unknown as (id: string | null) => void },
  mockMe: { value: null as unknown },
}));

vi.mock("@/queries/me", () => ({
  meQueryOptions: () => ({ queryKey: ["me"], queryFn: () => {} }),
}));

// useQuery must return a REAL ref (computed here) so Vue auto-unwrap
// works in templates. A plain { value: ... } object unwraps in scripts
// (explicit .value) but not in templates, which breaks v-for over
// me?.companies.
vi.mock("@tanstack/vue-query", async (orig) => {
  const actual = await orig<typeof import("@tanstack/vue-query")>();
  const { computed } = await import("vue");
  return {
    ...actual,
    useQuery: () => ({ data: computed(() => mockMe.value) }),
  };
});

vi.mock("@/queries/selects", () => ({
  useSelectCompanyMutation: () => ({ mutate: mockSelectCompany.mutate }),
  useSelectTeamMutation: () => ({ mutate: mockSelectTeam.mutate }),
}));

// Stub Select primitives to no-op wrappers. Named so tests can locate
// them via findAllComponents({ name: "Select" }) and drive
// update:modelValue directly — the API contract the picker depends on.
// The real reka-ui Select is a button trigger + portal, not a native
// <select>, so a <select> mock can't represent it correctly.
vi.mock("@/components/ui/select", () => ({
  Select: {
    name: "Select",
    props: ["modelValue"],
    emits: ["update:modelValue"],
    template: "<div><slot /></div>",
  },
  SelectTrigger: { template: "<div><slot /></div>" },
  SelectValue: { template: "<span><slot /></span>" },
  SelectContent: { template: "<div><slot /></div>" },
  SelectItem: {
    name: "SelectItem",
    props: ["value"],
    template: "<div><slot /></div>",
  },
}));

import ScopeContextPicker from "@/components/Schedule/ScopeContextPicker.vue";

function meFixture(
  overrides: Partial<{
    companies: { id: string; name: string }[];
    teams: { id: string; name: string }[];
    current_company_id: string | null;
    current_team_id: string | null;
  }> = {},
) {
  return {
    id: "u1",
    first_name: "Ada",
    last_name: "Lovelace",
    is_platform_admin: false,
    permissions: [],
    current_company_id: "c1",
    current_team_id: null,
    companies: [
      { id: "c1", name: "Acme" },
      { id: "c2", name: "Beta" },
    ],
    teams: [
      { id: "t1", name: "Kitchen" },
      { id: "t2", name: "Front" },
    ],
    available_scopes: ["team", "company"],
    ...overrides,
  };
}

beforeEach(() => {
  mockSelectCompany.mutate = vi.fn();
  mockSelectTeam.mutate = vi.fn();
  mockMe.value = meFixture();
});

function mountPicker(props: { scope: string }) {
  return mount(ScopeContextPicker, { props });
}

describe("ScopeContextPicker", () => {
  it("renders nothing with 1 company and 1 team", async () => {
    mockMe.value = meFixture({
      companies: [{ id: "c1", name: "Acme" }],
      teams: [{ id: "t1", name: "Kitchen" }],
    });
    const wrapper = mountPicker({ scope: "team" });
    await flushPromises();
    expect(wrapper.findAllComponents({ name: "Select" })).toHaveLength(0);
  });

  it("renders company picker when >1 company", async () => {
    const wrapper = mountPicker({ scope: "company" });
    await flushPromises();
    expect(wrapper.findAllComponents({ name: "Select" })).toHaveLength(1);
    const items = wrapper.findAllComponents({ name: "SelectItem" });
    expect(items).toHaveLength(2);
    expect(items.map((i) => i.text())).toEqual(["Acme", "Beta"]);
  });

  it("hides team picker on company scope", async () => {
    const wrapper = mountPicker({ scope: "company" });
    await flushPromises();
    expect(wrapper.findAllComponents({ name: "Select" })).toHaveLength(1);
  });

  it("renders team picker on team scope with >1 team", async () => {
    const wrapper = mountPicker({ scope: "team" });
    await flushPromises();
    expect(wrapper.findAllComponents({ name: "Select" })).toHaveLength(2);
  });

  it("renders team picker on me scope with >1 team", async () => {
    const wrapper = mountPicker({ scope: "me" });
    await flushPromises();
    expect(wrapper.findAllComponents({ name: "Select" })).toHaveLength(2);
  });

  it("calls selectCompany on company change", async () => {
    const wrapper = mountPicker({ scope: "company" });
    await flushPromises();
    const companySelect = wrapper.findAllComponents({ name: "Select" })[0]!;
    companySelect.vm.$emit("update:modelValue", "c2");
    await nextTick();
    expect(mockSelectCompany.mutate).toHaveBeenCalledWith("c2");
  });

  it("calls selectTeam on team change", async () => {
    const wrapper = mountPicker({ scope: "team" });
    await flushPromises();
    const selects = wrapper.findAllComponents({ name: "Select" });
    selects[1]!.vm.$emit("update:modelValue", "t2");
    await nextTick();
    expect(mockSelectTeam.mutate).toHaveBeenCalledWith("t2");
  });
});
