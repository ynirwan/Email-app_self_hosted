// frontend/src/api.js
//
// Centralised axios client with:
//   • access token attached on every request
//   • single-flight refresh on 401  (one /auth/refresh call in flight at a time;
//     all concurrent failing requests queue behind it and retry once it resolves)
//   • hard logout if the refresh itself returns 401  (revoked / deleted user)
//
// Token storage keys are intentionally namespaced (`auth.access`, `auth.refresh`)
// so a future migration away from localStorage only touches this file.
import axios from "axios";

const ACCESS_KEY = "token";              // legacy key kept for back-compat
const REFRESH_KEY = "refresh_token";

// ── Token helpers — exported so Login/Register/Logout don't poke localStorage ──

export function setTokens({ access, refresh }) {
  if (access) localStorage.setItem(ACCESS_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export function getAccessToken() {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY);
}

// ── Axios instance ──────────────────────────────────────────────────────────

const API = axios.create({ baseURL: "/api" });

API.interceptors.request.use(
  (config) => {
    const token = getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// ── Refresh state (single-flight) ───────────────────────────────────────────
//
// When several requests fire concurrently and all 401 (e.g. after the access
// token's 24h lifetime ticks over), we MUST NOT issue N parallel /auth/refresh
// calls — that races, may rotate the token mid-flight, and exhausts the
// refresh-token rate budget. Instead the first 401 starts a refresh; every
// subsequent 401 waits on the same promise and retries with the new token.

let _refreshPromise = null;

function _hardLogout() {
  clearTokens();
  // Avoid a redirect loop if we're already on /login.
  if (!window.location.pathname.startsWith("/login")) {
    window.location.assign("/login");
  }
}

async function _refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) {
    throw new Error("no_refresh_token");
  }

  // Use a bare axios call so we don't recurse through our own interceptors.
  const res = await axios.post("/api/auth/refresh", { refresh_token: refresh });
  const newAccess = res.data?.access_token || res.data?.token;
  if (!newAccess) {
    throw new Error("refresh_no_access_token");
  }
  localStorage.setItem(ACCESS_KEY, newAccess);
  return newAccess;
}

API.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status;
    const original = error.config;

    // Pass through everything except 401s on a request we can retry.
    if (status !== 401 || !original || original._retried) {
      return Promise.reject(error);
    }

    // Don't try to refresh the refresh endpoint itself, or login/register —
    // those 401s mean "credentials are bad", not "access token expired".
    const url = original.url || "";
    if (url.includes("/auth/refresh") || url.includes("/auth/login") || url.includes("/auth/register")) {
      if (url.includes("/auth/refresh")) {
        _hardLogout();
      }
      return Promise.reject(error);
    }

    original._retried = true;

    try {
      if (!_refreshPromise) {
        _refreshPromise = _refreshAccessToken().finally(() => {
          _refreshPromise = null;
        });
      }
      const newAccess = await _refreshPromise;
      original.headers = { ...(original.headers || {}), Authorization: `Bearer ${newAccess}` };
      return API(original);
    } catch (refreshErr) {
      // Refresh failed → token_version bumped, refresh expired, user deleted,
      // or no refresh token in storage. Give up cleanly.
      _hardLogout();
      return Promise.reject(refreshErr);
    }
  },
);

export default API;
