<script setup lang="ts">
defineProps<{ scopes: string[]; current: string }>();
defineEmits<{ select: [scope: string] }>();

const LABELS: Record<string, string> = {
  me: "Mine",
  team: "Team",
  company: "Company",
};

function labelFor(s: string): string {
  return LABELS[s] ?? s;
}
</script>

<template>
  <div
    v-if="scopes.length > 1"
    class="inline-flex overflow-hidden rounded-lg border border-border"
    role="tablist"
    aria-label="Schedule scope"
  >
    <button
      v-for="s in scopes"
      :key="s"
      type="button"
      role="tab"
      :aria-selected="s === current"
      :class="[
        'px-4 py-2 text-sm font-medium transition-colors',
        s === current
          ? 'bg-primary text-primary-foreground'
          : 'bg-background text-foreground hover:bg-muted',
      ]"
      @click="$emit('select', s)"
    >
      {{ labelFor(s) }}
    </button>
  </div>
</template>
