import { computed, ref } from "vue";
import { defineStore } from "pinia";

import { PERMS_KEY, TOKEN_KEY, USER_KEY } from "@/api/client";
import type { CurrentUserInfo } from "@/api/auth";

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export const useAuthStore = defineStore("auth", () => {
  const user = ref<CurrentUserInfo | null>(readJson<CurrentUserInfo>(USER_KEY));
  const permissions = ref<string[]>(readJson<string[]>(PERMS_KEY) ?? []);

  const isAuthed = computed(() => Boolean(localStorage.getItem(TOKEN_KEY)));

  function setSession(nextUser: CurrentUserInfo, nextPermissions: string[]) {
    user.value = nextUser;
    permissions.value = nextPermissions;
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser));
    localStorage.setItem(PERMS_KEY, JSON.stringify(nextPermissions));
  }

  function clearSession() {
    user.value = null;
    permissions.value = [];
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(PERMS_KEY);
  }

  function can(code: string): boolean {
    return permissions.value.includes(code);
  }

  return { user, permissions, isAuthed, setSession, clearSession, can };
});
