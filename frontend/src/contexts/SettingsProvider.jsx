// frontend/src/contexts/SettingsProvider.jsx
import { useEffect, useMemo, useCallback } from "react";
import { useUser } from "./UserContext";
import { SettingsContext, RTL_LANGUAGES } from "./SettingsContext";

import en from "../locales/en.json";
import es from "../locales/es.json";
import fr from "../locales/fr.json";
import de from "../locales/de.json";
import zh from "../locales/zh.json";
import hi from "../locales/hi.json";
import ar from "../locales/ar.json";
import ru from "../locales/ru.json";

import {
  formatDate as fmtDate,
  formatDateTime as fmtDateTime,
  formatTime as fmtTime,
  formatRelative as fmtRelative,
  formatNumber as fmtNumber,
} from "../utils/datetime";

const CATALOGS = { en, es, fr, de, zh, hi, ar, ru };
const SUPPORTED = Object.keys(CATALOGS);
const DEFAULT_LANGUAGE = "en";
const DEFAULT_TIMEZONE = "UTC";

const normalizeLang = (l) => {
  if (!l) return DEFAULT_LANGUAGE;
  const code = String(l).trim().toLowerCase().split("-")[0];
  return SUPPORTED.includes(code) ? code : DEFAULT_LANGUAGE;
};

export default function SettingsProvider({ children }) {
  const { user } = useUser() || {};

  const language = normalizeLang(user?.language);
  const timezone = user?.timezone || DEFAULT_TIMEZONE;
  const isRTL = RTL_LANGUAGES.has(language);

  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = isRTL ? "rtl" : "ltr";
  }, [language, isRTL]);

  const t = useCallback(
    (key, vars) => {
      const primary = CATALOGS[language] || CATALOGS[DEFAULT_LANGUAGE];
      const fallback = CATALOGS[DEFAULT_LANGUAGE];
      const template = primary[key] ?? fallback[key] ?? key;
      if (!vars) return template;
      return template.replace(/\{(\w+)\}/g, (_, name) =>
        vars[name] !== undefined ? String(vars[name]) : `{${name}}`
      );
    },
    [language]
  );

  const value = useMemo(
    () => ({
      timezone,
      language,
      isRTL,
      supportedLanguages: SUPPORTED,
      t,
      formatDate: (input) => fmtDate(input, { timezone, language }),
      formatDateTime: (input) => fmtDateTime(input, { timezone, language }),
      formatTime: (input) => fmtTime(input, { timezone, language }),
      formatRelative: (input) => fmtRelative(input, { language }),
      formatNumber: (n, opts) => fmtNumber(n, { language, ...opts }),
    }),
    [timezone, language, isRTL, t]
  );

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}