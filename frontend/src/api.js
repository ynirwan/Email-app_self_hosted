// frontend/src/api.js
//
// Centralised axios client.
//
// Auth model (post BUG-11 fix):
//   • The access token lives in an httpOnly SameSite=Strict cookie — JS never
//     sees or stores the raw JWT, so XSS cannot exfiltrate it.
//   • The refresh token lives in an httpOnly cookie scoped to /api/auth/refresh.
//   • A non-httpOnly `logged_in=1` flag cookie is set alongside the JWTs so the
//     frontend can cheaply detect an active session without a round-trip.
//   • withCredentials: true tells axios to send cookies with every request.
//   • The single-flight refresh mechanism is preserved — one concurrent /refresh
//     call at most, all other concurrent 401s wait behind it.
//
// localStorage is NOT used for tokens. Callers that previously called
// setTokens() / getAccessToken() should be updated; those functions now no-op
// or read the flag cookie only.

import axios from "axios";

// ── Session flag cookie ─────────────────────────────────────────────────────
// The actual JWT is httpOnly — JS cannot read it. This non-httpOnly flag cookie
// signals "an auth session exists" so App.jsx can gate routes without a fetch.

export function isLoggedIn() {
  return document.cookie.split(";").some((c) => c.trim().startsWith("logged_in="));
}

// Legacy no-ops kept so callers don't break during the migration.
// Remove once all call-sites are updated.
export function setTokens() {}
export function clearTokens() {}
export function getAccessToken() { return null; }
export function getRefreshToken() { return null; }

// ── Axios instance ──────────────────────────────────────────────────────────

const API = axios.create({
  baseURL: "/api",
  withCredentials: true,   // send auth cookies with every request
});

// No request interceptor needed — cookies are attached by the browser automatically.

// ── Refresh state (single-flight) ───────────────────────────────────────────
//
// When several requests fire concurrently and all 401 (access token expired),
// only one /auth/refresh call is issued. The others queue behind it and retry
// once the new access-token cookie has been set.

let _refreshPromise = null;

function _hardLogout() {
  // Clear the JS-readable session flag so the route gate flips immediately.
  document.cookie = "logged_in=; path=/; max-age=0; SameSite=Strict";
  if (!window.location.pathname.startsWith("/login")) {
    window.location.assign("/login");
  }
}

async function _refreshAccessToken() {
  // POST with no body — the refresh token cookie is sent automatically.
  await axios.post("/api/auth/refresh", {}, { withCredentials: true });
  // If the server returned 200 it has set a new access_token cookie already.
}

API.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status;
    const original = error.config;

    if (status !== 401 || !original || original._retried) {
      return Promise.reject(error);
    }

    // Don't attempt refresh for auth endpoints themselves.
    const url = original.url || "";
    if (
      url.includes("/auth/refresh") ||
      url.includes("/auth/login") ||
      url.includes("/auth/register")
    ) {
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
      await _refreshPromise;
      // No need to update the Authorization header — the cookie was refreshed
      // server-side and will be included in the retry automatically.
      return API(original);
    } catch (refreshErr) {
      _hardLogout();
      return Promise.reject(refreshErr);
    }
  },
);

export default API;
