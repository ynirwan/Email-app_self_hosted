// frontend/src/utils/datetime.js
//
// Pure date/time formatters. Read by SettingsContext — components should
// call the hook (`useSettings().formatDateTime`) rather than importing
// these directly, so the user's timezone/language stays consistent.

const DEFAULT_TZ = "UTC";
const DEFAULT_LOCALE = "en";

// Map our short language codes to full BCP 47 locales used by Intl.
const LOCALE_MAP = {
  en: "en-US",
  es: "es-ES",
  fr: "fr-FR",
  de: "de-DE",
  zh: "zh-CN",
  hi: "hi-IN",
  ar: "ar-SA",  
  ru: "ru-RU", 
};

const toBCP47 = (lang) => LOCALE_MAP[lang] || LOCALE_MAP[DEFAULT_LOCALE];

const safeDate = (input) => {
  if (input == null || input === "") return null;
  const d = input instanceof Date ? input : new Date(input);
  return Number.isNaN(d.getTime()) ? null : d;
};

/** "Nov 24, 2024" — date-only, in user's tz/locale. */
export function formatDate(input, { timezone = DEFAULT_TZ, language = DEFAULT_LOCALE } = {}) {
  const d = safeDate(input);
  if (!d) return "—";
  try {
    return new Intl.DateTimeFormat(toBCP47(language), {
      timeZone: timezone,
      year: "numeric",
      month: "short",
      day: "numeric",
    }).format(d);
  } catch {
    return d.toISOString().slice(0, 10);
  }
}

/** "Nov 24, 2024, 3:42 PM" — date + time, in user's tz/locale. */
export function formatDateTime(input, { timezone = DEFAULT_TZ, language = DEFAULT_LOCALE } = {}) {
  const d = safeDate(input);
  if (!d) return "—";
  try {
    return new Intl.DateTimeFormat(toBCP47(language), {
      timeZone: timezone,
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return d.toISOString();
  }
}

/** "3:42 PM" — time-only, in user's tz/locale. */
export function formatTime(input, { timezone = DEFAULT_TZ, language = DEFAULT_LOCALE } = {}) {
  const d = safeDate(input);
  if (!d) return "—";
  try {
    return new Intl.DateTimeFormat(toBCP47(language), {
      timeZone: timezone,
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return "—";
  }
}

/** "2 hours ago", "in 3 days" — uses Intl.RelativeTimeFormat. */
export function formatRelative(input, { language = DEFAULT_LOCALE } = {}) {
  const d = safeDate(input);
  if (!d) return "—";
  const diffSec = Math.round((d.getTime() - Date.now()) / 1000);
  const abs = Math.abs(diffSec);
  const rtf = new Intl.RelativeTimeFormat(toBCP47(language), { numeric: "auto" });

  const units = [
    ["year",   60 * 60 * 24 * 365],
    ["month",  60 * 60 * 24 * 30],
    ["day",    60 * 60 * 24],
    ["hour",   60 * 60],
    ["minute", 60],
    ["second", 1],
  ];
  for (const [unit, secInUnit] of units) {
    if (abs >= secInUnit || unit === "second") {
      return rtf.format(Math.round(diffSec / secInUnit), unit);
    }
  }
  return rtf.format(0, "second");
}

/** "1,234.5" — locale-aware number formatting. */
export function formatNumber(value, { language = DEFAULT_LOCALE, ...options } = {}) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  try {
    return new Intl.NumberFormat(toBCP47(language), options).format(n);
  } catch {
    return String(n);
  }
}