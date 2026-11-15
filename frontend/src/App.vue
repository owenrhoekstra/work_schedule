<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import { Toaster } from "@/components/ui/sonner";
import MenuBar from "./components/MenuBar.vue";
import PageSkeleton from "./components/PageSkeleton.vue";
import "vue-sonner/style.css";

const router = useRouter();
const route = useRoute();

// Resolves when the first navigation finishes: the guard has loaded the user
// and the route's lazy-loaded view has downloaded.
const ready = ref(false);
router.isReady().finally(() => (ready.value = true));

// Public pages (login) get no menu bar or page container. Before the first
// navigation finishes `route` is empty, so work it out from the URL instead.
const isPublic = computed(() => {
  const current = route.matched.length ? route : router.resolve(window.location.pathname);
  return Boolean(current.meta.public);
});
</script>

<template>
  <MenuBar v-if="!isPublic" />

  <div :class="[!isPublic && 'w-full mx-auto px-4 xl:px-8 max-w-7xl']">
    <main id="main-content" tabindex="-1" :class="['outline-none', !isPublic && 'w-full p-6']">
      <PageSkeleton v-if="!ready && !isPublic" />
      <RouterView />
      <Toaster rich-colors position="bottom-right" />
    </main>
  </div>
</template>

<style scoped></style>
