<script setup lang="ts">
import { PhCalendarDots, PhGear, PhSignOut, PhUser } from "@phosphor-icons/vue";
import { useQuery } from "@tanstack/vue-query";
import { computed } from "vue";
import { RouterLink } from "vue-router";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { meQueryOptions } from "@/queries/me";

const { data: me, isPending } = useQuery(meQueryOptions());

const fullName = computed(() =>
  me.value ? `${me.value.first_name} ${me.value.last_name}`.trim() : "",
);

// Shared classes. Complete strings, so Tailwind still detects them.
const touchTarget = "max-sm:min-h-11 max-sm:min-w-11";
const highlightHover = "hover:bg-highlight hover:text-primary-foreground dark:hover:bg-highlight";
const primaryHover = "hover:bg-primary hover:text-primary-foreground dark:hover:bg-primary";

// Big on phones, normal size from the sm breakpoint up
const iconSize = "size-6 sm:size-4";

const skipToContent = () => {
  const main = document.getElementById("main-content");
  main?.focus();
  main?.scrollIntoView();
};

// Django's LogoutView is POST-only + CSRF-protected. Read the token
// from the cookie (set by CsrfViewMiddleware / the shell template).
const csrfToken = (() => {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return m && m[1] ? decodeURIComponent(m[1]) : "";
})();
</script>

<template>
  <header class="border-b border-border bg-card text-card-foreground">
    <a
      href="#main-content"
      class="sr-only rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground focus:not-sr-only focus:fixed focus:left-4 focus:top-2 focus:z-50"
      @click.prevent="skipToContent"
    >
      Skip to main content
    </a>

    <div class="mx-auto flex h-14 max-w-375 items-center gap-4 px-8 sm:gap-6">
      <nav aria-label="Main">
        <Button as-child variant="outline" :class="[highlightHover, touchTarget]">
          <RouterLink :to="{ name: 'schedule' }">
            <PhCalendarDots />
            Schedule
          </RouterLink>
        </Button>
      </nav>

      <div class="ml-auto flex min-w-0 items-center gap-4">
        <div class="mr-2 min-w-0 sm:mr-4" aria-live="polite">
          <Skeleton v-if="isPending" class="h-5 w-24 sm:w-36" aria-hidden="true" />
          <span v-if="isPending" class="sr-only">Loading your name</span>
          <p v-else class="truncate">
            {{ fullName ? `Hello, ${fullName}!` : "Hello!" }}
          </p>
        </div>

        <nav aria-label="Account" class="flex items-center gap-4">
          <Button as-child variant="outline" :class="[highlightHover, touchTarget]">
            <a href="/accounts/profile/">
              <PhUser :class="iconSize" aria-hidden="true" />
              <span class="sr-only sm:not-sr-only">Profile</span>
            </a>
          </Button>

          <Button as-child variant="outline" :class="[highlightHover, touchTarget]">
            <a href="/schedule/settings/">
              <PhGear :class="iconSize" aria-hidden="true" />
              <span class="sr-only sm:not-sr-only">Settings</span>
            </a>
          </Button>
        </nav>

        <form method="post" action="/accounts/logout/" class="inline-flex">
          <input type="hidden" name="csrfmiddlewaretoken" :value="csrfToken" />
          <Button type="submit" variant="outline" :class="[primaryHover, touchTarget]">
            <PhSignOut :class="iconSize" aria-hidden="true" />
            <span class="sr-only sm:not-sr-only">Log Out</span>
          </Button>
        </form>
      </div>
    </div>
  </header>
</template>
