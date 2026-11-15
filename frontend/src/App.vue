<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import { Toaster } from "@/components/ui/sonner";
import MenuBar from "./components/MenuBar.vue";
import PageSkeleton from "./components/PageSkeleton.vue";
import "vue-sonner/style.css";

const route = useRoute();
const router = useRouter();

// Resolves when the first navigation finishes. Before that, `route`
// is empty and any attempt to infer the current route from the URL
// is unreliable — the shell just renders a skeleton until ready.
const ready = ref(false);
router.isReady().finally(() => (ready.value = true));

// MenuBar + page container only on non-public, ready routes. On the
// login shell: ready + public => no chrome.
const showChrome = computed(() => ready.value && !route.meta.public);
</script>

<template>
  <MenuBar v-if="showChrome" />

  <div :class="[showChrome && 'w-full mx-auto px-4 xl:px-8 max-w-7xl']">
    <main id="main-content" tabindex="-1" :class="['outline-none', showChrome && 'w-full p-6']">
      <PageSkeleton v-if="!ready" />
      <RouterView v-else />
      <Toaster rich-colors position="bottom-right" />
    </main>
  </div>
</template>
