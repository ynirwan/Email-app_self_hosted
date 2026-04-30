import { useState, useEffect } from "react";
import API from "../api";
import { useUser } from "../contexts/UserContext";
import { useSettings } from "../contexts/SettingsContext";

const LANGUAGES = [
  { code: "en", name: "English" },
  { code: "es", name: "Español" },
  { code: "fr", name: "Français" },
  { code: "de", name: "Deutsch" },
  { code: "zh", name: "中文" },
  { code: "hi", name: "हिन्दी" },
  { code: "ar", name: "العربية" },
  { code: "ru", name: "Русский" },
];

// Intl.supportedValuesOf is available in modern browsers; fallback list keeps
// older browsers usable.
const ALL_TIMEZONES =
  typeof Intl.supportedValuesOf === "function"
    ? Intl.supportedValuesOf("timeZone")
    : [
        "UTC",
        "America/New_York",
        "America/Los_Angeles",
        "Europe/London",
        "Europe/Berlin",
        "Asia/Kolkata",
        "Asia/Tokyo",
        "Australia/Sydney",
      ];

export default function UserSettings() {
  const { refetchUser } = useUser();
  const { t } = useSettings();

  const [user, setUser] = useState({ name: "", email: "", timezone: "UTC", language: "en" });
  const [passwords, setPasswords] = useState({
    current_password: "",
    new_password: "",
    confirm_password: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null); // { type: 'success' | 'error', text }

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const res = await API.get("/auth/me");
        if (mounted) setUser(res.data);
      } catch (err) {
        console.error("Failed to fetch user:", err);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const showMsg = (type, text) => {
    setMsg({ type, text });
    setTimeout(() => setMsg(null), 3000);
  };

  const handleUpdateProfile = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await API.put("/auth/me", {
        name: user.name,
        email: user.email,
        timezone: user.timezone,
        language: user.language,
      });
      // Refetch so UserContext (and SettingsContext via it) reflect the new values.
      if (refetchUser) await refetchUser();
      showMsg("success", t("settings.profile.updated"));
    } catch (err) {
      showMsg("error", err.response?.data?.detail || t("common.error"));
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (passwords.new_password !== passwords.confirm_password) {
      showMsg("error", t("settings.password.mismatch"));
      return;
    }
    setSaving(true);
    try {
      await API.put("/auth/me/password", {
        current_password: passwords.current_password,
        new_password: passwords.new_password,
      });
      setPasswords({ current_password: "", new_password: "", confirm_password: "" });
      showMsg("success", t("settings.password.updated"));
    } catch (err) {
      showMsg("error", err.response?.data?.detail || t("common.error"));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div>{t("common.loading")}</div>;

  return (
    <div className="max-w-4xl space-y-8">
      {msg && (
        <div
          className={`px-4 py-3 rounded-lg text-sm font-medium ${
            msg.type === "success"
              ? "bg-green-50 border border-green-200 text-green-800"
              : "bg-red-50 border border-red-200 text-red-800"
          }`}
        >
          {msg.text}
        </div>
      )}

      <section className="bg-white p-6 rounded-lg shadow">
        <h2 className="text-xl font-bold mb-4">{t("settings.profile")}</h2>
        <form onSubmit={handleUpdateProfile} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium">{t("settings.name")}</label>
              <input
                type="text"
                className="w-full p-2 border rounded"
                value={user.name || ""}
                onChange={(e) => setUser({ ...user, name: e.target.value })}
              />
            </div>
            <div>
              <label className="block text-sm font-medium">{t("settings.email")}</label>
              <input
                type="email"
                className="w-full p-2 border rounded"
                value={user.email || ""}
                onChange={(e) => setUser({ ...user, email: e.target.value })}
              />
            </div>
            <div>
              <label className="block text-sm font-medium">{t("settings.timezone")}</label>
              <select
                className="w-full p-2 border rounded"
                value={user.timezone || "UTC"}
                onChange={(e) => setUser({ ...user, timezone: e.target.value })}
              >
                {ALL_TIMEZONES.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium">{t("settings.language")}</label>
              <select
                className="w-full p-2 border rounded"
                value={user.language || "en"}
                onChange={(e) => setUser({ ...user, language: e.target.value })}
              >
                {LANGUAGES.map((lang) => (
                  <option key={lang.code} value={lang.code}>
                    {lang.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button
            type="submit"
            disabled={saving}
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? t("common.saving") : t("common.save")}
          </button>
        </form>
      </section>

      <section className="bg-white p-6 rounded-lg shadow">
        <h2 className="text-xl font-bold mb-4">{t("settings.password.title")}</h2>
        <form onSubmit={handleChangePassword} className="space-y-4 max-w-md">
          <div>
            <label className="block text-sm font-medium">
              {t("settings.password.current")}
            </label>
            <input
              type="password"
              className="w-full p-2 border rounded"
              value={passwords.current_password}
              onChange={(e) =>
                setPasswords({ ...passwords, current_password: e.target.value })
              }
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium">
              {t("settings.password.new")}
            </label>
            <input
              type="password"
              className="w-full p-2 border rounded"
              value={passwords.new_password}
              onChange={(e) =>
                setPasswords({ ...passwords, new_password: e.target.value })
              }
              required
              minLength={8}
            />
          </div>
          <div>
            <label className="block text-sm font-medium">
              {t("settings.password.confirm")}
            </label>
            <input
              type="password"
              className="w-full p-2 border rounded"
              value={passwords.confirm_password}
              onChange={(e) =>
                setPasswords({ ...passwords, confirm_password: e.target.value })
              }
              required
              minLength={8}
            />
          </div>
          <button
            type="submit"
            disabled={saving}
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? t("common.saving") : t("common.save")}
          </button>
        </form>
      </section>
    </div>
  );
}