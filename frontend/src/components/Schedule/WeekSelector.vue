<script setup lang="ts">
import { type DateValue, parseDate, startOfWeek } from "@internationalized/date";
import { computed, ref } from "vue";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { WeekRef } from "@/types/week";

const props = defineProps<{ week: WeekRef }>();
const emit = defineEmits<{ navigate: [week: string] }>();

const open = ref(false);
const monday = computed(() => startOfWeek(parseDate(props.week.start), "en-GB"));

function onSelect(d: DateValue | undefined) {
  if (!d) return;
  emit("navigate", startOfWeek(d, "en-GB").toString());
  open.value = false;
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <Button
        variant="ghost"
        class="h-auto px-2 py-1 font-[inherit] text-[length:inherit] font-[inherit]"
      >
        <slot />
      </Button>
    </PopoverTrigger>
    <PopoverContent
      class="w-auto border-2 border-foreground/25 p-0 shadow-xl"
      align="center"
      :side-offset="4"
    >
      <Calendar
        :model-value="monday"
        :placeholder="monday"
        :week-starts-on="1"
        prevent-deselect
        @update:model-value="onSelect"
      />
    </PopoverContent>
  </Popover>
</template>
