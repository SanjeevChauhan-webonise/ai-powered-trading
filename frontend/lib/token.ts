import { STORAGE_PREFIX } from "./brand";

const KEY = `${STORAGE_PREFIX}:token`;

export function getToken(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(KEY, token);
  } catch {
    /* storage blocked: the login only lasts until the page is closed */
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* nothing to clear */
  }
}
