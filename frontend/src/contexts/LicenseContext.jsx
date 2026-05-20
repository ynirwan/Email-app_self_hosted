// frontend/src/contexts/LicenseContext.jsx
//
// Fetches /api/license/status once after login and exposes plan + feature flags
// to the entire app.  Components use useLicense() to gate UI elements without
// making their own API calls.
//
// The context deliberately does NOT block rendering while loading — it defaults
// to "all features enabled" during the brief fetch so the page doesn't flash a
// locked state on first load for legitimate users.

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";
import API, { getAccessToken } from "../api";

const LicenseContext = createContext(null);

/** Sentinel default — treat as "all enabled" while loading or on error */
const _DEFAULT = {
  loading: true,
  valid: true,
  plan: "professional",
  features: {},
  expiresAt: null,
  daysUntilExpiry: null,
  isExpired: false,
  error: null,
};

export function LicenseProvider({ children }) {
  const [license, setLicense] = useState(_DEFAULT);

  const fetchLicense = useCallback(async () => {
    if (!getAccessToken()) {
      setLicense({ ..._DEFAULT, loading: false });
      return;
    }
    try {
      const res = await API.get("/license/status");
      const d = res.data;
      setLicense({
        loading: false,
        valid: d.valid ?? true,
        plan: d.plan ?? "starter",
        features: d.features ?? {},
        expiresAt: d.expires_at ?? null,
        daysUntilExpiry: d.days_until_expiry ?? null,
        isExpired: d.is_expired ?? false,
        error: d.error ?? null,
      });
    } catch {
      // Network failure or non-401 error — don't lock the user out.
      setLicense({ ..._DEFAULT, loading: false });
    }
  }, []);

  useEffect(() => {
    fetchLicense();
  }, [fetchLicense]);

  return (
    <LicenseContext.Provider value={{ license, refetchLicense: fetchLicense }}>
      {children}
    </LicenseContext.Provider>
  );
}

export function useLicense() {
  return useContext(LicenseContext);
}

/**
 * isFeatureEnabled(feature, license)
 *
 * Utility for checking a single feature flag outside of React components
 * (e.g. in route guards).  Pass the license object from useLicense().
 *
 * Returns true while loading (optimistic default) to avoid flickering locked
 * states for users who do have access.
 */
export function isFeatureEnabled(feature, license) {
  if (!license || license.loading) return true; // optimistic while loading
  const val = license.features[feature];
  if (val === undefined) return false;
  if (typeof val === "boolean") return val;
  if (typeof val === "number") return val !== 0; // -1 = unlimited = enabled
  return Boolean(val);
}
