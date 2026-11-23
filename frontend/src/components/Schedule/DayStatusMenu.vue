<script setup lang="ts">
import { PhDotsThreeVertical } from "@phosphor-icons/vue";
import { ref } from "vue";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { type DayOverrideVars, useDayOverrideMutation } from "@/queries/overrides";

const props = defineProps<{
  date: string;
  label: string;
  status: string | null;
  editable: boolean;
}>();

const open = ref(false);
const mutation = useDayOverrideMutation();

function apply(action: DayOverrideVars["action"]) {
  mutation.mutate({ date: props.date, action }, { onSuccess: () => (open.value = false) });
}
</script>

<template>
  <Popover v-if="editable" v-model:open="open">
    <PopoverTrigger as-child>
      <button
        type="button"
        class="flex w-full cursor-pointer items-center justify-center gap-1 rounded-md px-1 py-1 text-current transition-colors hover:bg-white/15 focus-visible:ring-2 focus-visible:ring-white/50 focus-visible:outline-none"
        :aria-label="`Day status for ${label}`"
      >
        <span class="flex flex-col"><slot /></span>
        <PhDotsThreeVertical class="size-5 shrink-0" weight="bold" aria-hidden="true" />
      </button>
    </PopoverTrigger>
    <PopoverContent
      class="w-40 border-2 border-foreground/25 p-1 shadow-xl"
      align="center"
      :side-offset="4"
    >
      <div class="flex flex-col text-foreground">
        <Button
          v-if="status !== 'closed'"
          variant="ghost"
          size="sm"
          class="justify-start"
          :disabled="mutation.isPending.value"
          @click="apply('closed')"
          >Mark closed</Button
        >
        <Button
          v-if="status !== 'holiday'"
          variant="ghost"
          size="sm"
          class="justify-start"
          :disabled="mutation.isPending.value"
          @click="apply('holiday')"
          >Mark holiday</Button
        >
        <Button
          v-if="status"
          variant="ghost"
          size="sm"
          class="justify-start"
          :disabled="mutation.isPending.value"
          @click="apply('clear')"
          >Clear status</Button
        >
      </div>
    </PopoverContent>
  </Popover>
  <div v-else class="flex flex-col"><slot /></div>
</template>
