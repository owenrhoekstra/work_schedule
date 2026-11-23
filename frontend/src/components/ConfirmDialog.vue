<script setup lang="ts">
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

defineProps<{
  title: string;
  description: string;
  open: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  approved: [];
  cancelled: [];
}>();

function handleApproved() {
  emit("approved");
  emit("update:open", false);
}

function handleCancelled() {
  emit("cancelled");
  emit("update:open", false);
}

function handleOpenChange(value: boolean) {
  if (!value) {
    handleCancelled();
  } else {
    emit("update:open", true);
  }
}
</script>

<template>
  <AlertDialog :open="open" @update:open="handleOpenChange">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>
          {{ title }}
        </AlertDialogTitle>

        <AlertDialogDescription>
          {{ description }}
        </AlertDialogDescription>
      </AlertDialogHeader>

      <AlertDialogFooter>
        <AlertDialogCancel @click="handleCancelled"> Cancel </AlertDialogCancel>

        <AlertDialogAction @click="handleApproved"> Confirm </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
