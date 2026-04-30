// frontend/src/contexts/SettingsContext.js
import { createContext, useContext } from "react";
import {
  formatDate as fmtDate,
  formatDateTime as fmtDateTime,
  formatTime as fmtTime,
  formatRelative as fmtRelative,
  formatNumber as fmtNumber,
} from "../utils/datetime";

const DEFAULT_LANGUAGE = "en";
const DEFAULT_TIMEZONE = "UTC";

export const RTL_LANGUAGES = new Set(["ar"]);

export const SettingsContext = createContext(null);

export function useSettings() {
  const ctx = useContext(SettingsContext);
  if (!ctx) {
    // Defensive fallback — keeps components working outside the provider
    // (e.g. isolated unit tests, Storybook).
    return {
      timezone: DEFAULT_TIMEZONE,
      language: DEFAULT_LANGUAGE,
      isRTL: false,
      supportedLanguages: ["en", "es", "fr", "de", "zh", "hi", "ar", "ru"],
      t: (key) => key,
      formatDate: (input) => fmtDate(input, {}),
      formatDateTime: (input) => fmtDateTime(input, {}),
      formatTime: (input) => fmtTime(input, {}),
      formatRelative: (input) => fmtRelative(input, {}),
      formatNumber: (n, opts) => fmtNumber(n, opts),
    };
  }
  return ctx;
}