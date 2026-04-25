// frontend/src/pages/EmailSettings.jsx
import { useState, useEffect } from "react";
import API from "../api";

export default function EmailSettings() {
  const [systemInfo, setSystemInfo] = useState(null);
  const [settings, setSettings] = useState({
    smtp_choice: "managed",
    provider: "",
    smtp_server: "",
    smtp_port: 587,
    username: "",
    password: "",
    ses_type: null,
    aws_region: "us-east-1",
    ses_configuration_set: "",
    bounce_forward_email: "",
  });
  const [usage, setUsage] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saveMsg, setSaveMsg] = useState(null); // { type, text }
  const [testMsg, setTestMsg] = useState(null);
  const [loadErr, setLoadErr] = useState(null);
  // FIX: track whether user actually typed a new password
  const [passwordEdited, setPasswordEdited] = useState(false);

  const isHostedService = systemInfo?.deployment_mode === "hosted_service";

  // ── Provider configs ───────────────────────────────────────────────────────
  const providerConfigs = {
    sendgrid: {
      name: "SendGrid",
      smtp_server: "smtp.sendgrid.net",
      smtp_port: 587,
      usernameLabel: "API Key",
      passwordLabel: "Password",
      helpText: "Use your SendGrid API key as the username",
    },
    mailgun: {
      name: "Mailgun",
      smtp_server: "smtp.mailgun.org",
      smtp_port: 587,
      usernameLabel: "Username",
      passwordLabel: "Password",
      helpText: "Get SMTP credentials from your Mailgun dashboard",
    },
    postmark: {
      name: "Postmark",
      smtp_server: "smtp.postmarkapp.com",
      smtp_port: 587,
      usernameLabel: "Server API Token",
      passwordLabel: "Server API Token",
      helpText: "Use the same Server API Token for both fields",
    },
    custom: {
      name: "Custom SMTP",
      smtp_server: "",
      smtp_port: 587,
      usernameLabel: "Username",
      passwordLabel: "Password",
      helpText: "Configure your custom SMTP server",
    },
  };

  const awsRegions = [
    { value: "us-east-1", label: "US East (N. Virginia)" },
    { value: "us-west-2", label: "US West (Oregon)" },
    { value: "eu-west-1", label: "Europe (Ireland)" },
    { value: "eu-central-1", label: "Europe (Frankfurt)" },
    { value: "ap-south-1", label: "Asia Pacific (Mumbai)" },
    { value: "ap-southeast-1", label: "Asia Pacific (Singapore)" },
    { value: "ap-southeast-2", label: "Asia Pacific (Sydney)" },
    { value: "ap-northeast-1", label: "Asia Pacific (Tokyo)" },
  ];

  // ── Data loading ───────────────────────────────────────────────────────────
  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoadErr(null);
    try {
      setLoading(true);
      const [sysRes, settingsRes] = await Promise.all([
        API.get("/email/system-info"),
        API.get("/email/settings"),
      ]);
      setSystemInfo(sysRes.data);
      setSettings(settingsRes.data);
      // FIX: password comes back as "********" — reset edit flag so we don't
      // re-send the masked value on next save
      setPasswordEdited(false);
      if (sysRes.data.deployment_mode === "hosted_service") {
        try {
          const r = await API.get("/email/usage");
          setUsage(r.data);
        } catch {
          /* optional */
        }
      }
    } catch {
      setLoadErr("Failed to load email settings. Please refresh.");
    } finally {
      setLoading(false);
    }
  };

  // ── Provider / SES handlers ────────────────────────────────────────────────
  const handleProviderChange = (provider) => {
    const cfg = providerConfigs[provider];
    if (provider === "amazonses") {
      setSettings((p) => ({
        ...p,
        provider: "amazonses",
        ses_type: null,
        smtp_server: "",
        smtp_port: 587,
        aws_region: "us-east-1",
      }));
    } else if (cfg) {
      setSettings((p) => ({
        ...p,
        provider,
        smtp_server: cfg.smtp_server,
        smtp_port: cfg.smtp_port,
        ses_type: null,
      }));
    }
    // Changing provider means the saved password no longer applies
    setPasswordEdited(false);
  };

  const handleSESTypeChange = (sesType) => {
    setSettings((p) => ({
      ...p,
      ses_type: sesType,
      smtp_server:
        sesType === "smtp" ? `email-smtp.${p.aws_region}.amazonaws.com` : "",
      smtp_port: 587,
    }));
  };

  const handleAWSRegionChange = (region) => {
    setSettings((p) => ({
      ...p,
      aws_region: region,
      smtp_server:
        p.ses_type === "smtp"
          ? `email-smtp.${region}.amazonaws.com`
          : p.smtp_server,
    }));
  };

  // ── Validation helper ──────────────────────────────────────────────────────
  const validateSmtp = () => {
    const needsSmtp = !isHostedService || settings.smtp_choice === "client";
    if (!needsSmtp) return null;

    if (!settings.provider) return "Please select an email provider.";
    if (!settings.smtp_server && settings.provider !== "amazonses")
      return "SMTP server is required.";
    if (settings.provider === "amazonses" && !settings.ses_type)
      return "Please choose SES API or SES SMTP mode.";
    if (!settings.username) return "Username / API key is required.";
    // Only block save if no password has ever been set AND user hasn't typed one
    if (
      !settings.password ||
      (settings.password === "********" && !passwordEdited)
    )
      return null; // existing password is fine
    return null;
  };

  // ── Save ───────────────────────────────────────────────────────────────────
  const saveSettings = async () => {
    setSaveMsg(null);

    const validationError = validateSmtp();
    if (validationError) {
      setSaveMsg({ type: "error", text: validationError });
      return;
    }

    // FIX: build payload — omit password if user hasn't changed it, so we
    // never accidentally store the masked "********" string
    const payload = {
      ...settings,
      smtp_port: parseInt(settings.smtp_port, 10) || 587, // always integer
    };
    if (!passwordEdited) {
      delete payload.password; // backend keeps existing encrypted password
    }

    setSaving(true);
    try {
      await API.put("/email/settings", payload);
      setSaveMsg({
        type: "success",
        text: "Email settings saved successfully!",
      });
      setPasswordEdited(false);
      // FIX: don't call fetchData() here — it would overwrite state with the
      // masked password again and trigger a stale-password save next time.
    } catch (err) {
      setSaveMsg({
        type: "error",
        text: err.response?.data?.detail || "Failed to save settings.",
      });
    } finally {
      setSaving(false);
    }
  };

  // ── Test connection ────────────────────────────────────────────────────────
  const testConnection = async () => {
    setTestMsg(null);

    if (!settings.smtp_server) {
      setTestMsg({ type: "error", text: "SMTP server is required to test." });
      return;
    }
    if (!settings.username) {
      setTestMsg({ type: "error", text: "Username is required to test." });
      return;
    }

    setTesting(true);
    try {
      // FIX: smtp_port as integer; password as-is — backend handles "********"
      // by reading the stored encrypted value
      const res = await API.post("/email/test-connection", {
        provider: settings.provider,
        smtp_server: settings.smtp_server,
        smtp_port: parseInt(settings.smtp_port, 10) || 587,
        username: settings.username,
        password: settings.password,
        ses_type: settings.ses_type,
        aws_region: settings.aws_region,
      });
      setTestMsg({
        type: "success",
        text: res.data.message || "Connection successful!",
      });
    } catch (err) {
      setTestMsg({
        type: "error",
        text: err.response?.data?.detail || "Connection test failed.",
      });
    } finally {
      setTesting(false);
    }
  };

  // ── Loading / error guards ─────────────────────────────────────────────────
  if (loading)
    return (
      <div className="flex items-center justify-center h-64 gap-3 text-gray-400">
        <div className="animate-spin h-5 w-5 border-2 border-gray-300 border-t-blue-500 rounded-full" />
        Loading email settings…
      </div>
    );

  if (loadErr)
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm flex items-center gap-3">
        ⚠️ {loadErr}
        <button onClick={fetchData} className="underline ml-2">
          Retry
        </button>
      </div>
    );

  const currentProviderCfg =
    providerConfigs[settings.provider] || providerConfigs.custom;
  const showSmtpConfig = isHostedService
    ? settings.smtp_choice === "client"
    : true;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-4xl space-y-6">
      {/* Deployment banner */}
      <div className="bg-blue-50 border border-blue-200 px-4 py-3 rounded-lg text-sm text-blue-800">
        <strong>Deployment Mode:</strong>{" "}
        {isHostedService ? "☁️ Hosted Service" : "🏠 Self-Hosted"} ·{" "}
        {isHostedService
          ? "Managed infrastructure — quota enforced per your subscription plan."
          : "Full control over email sending — connect any SMTP provider."}
      </div>

      {/* SMTP choice (hosted only) */}
      {isHostedService && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            SMTP Configuration Type
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              {
                value: "managed",
                label: "🚀 Managed SMTP",
                desc: "Premium email service managed by us",
                points: [
                  "High deliverability",
                  "Managed infrastructure",
                  "Quota based on plan",
                ],
                color: "green",
              },
              {
                value: "client",
                label: "⚙️ Your SMTP",
                desc: "Use your own SMTP provider",
                points: [
                  "Full control",
                  "Use your own provider",
                  "No additional cost",
                ],
                color: "blue",
              },
            ].map((opt) => (
              <div
                key={opt.value}
                onClick={() =>
                  setSettings((p) => ({ ...p, smtp_choice: opt.value }))
                }
                className={`p-5 border-2 rounded-xl cursor-pointer transition-all ${
                  settings.smtp_choice === opt.value
                    ? `border-${opt.color}-500 bg-${opt.color}-50`
                    : "border-gray-200 hover:border-gray-300"
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <input
                    type="radio"
                    readOnly
                    checked={settings.smtp_choice === opt.value}
                    className="flex-shrink-0"
                  />
                  <span className="text-sm font-semibold">{opt.label}</span>
                </div>
                <p className="text-xs text-gray-500 mb-3">{opt.desc}</p>
                <ul className="space-y-1">
                  {opt.points.map((pt) => (
                    <li
                      key={pt}
                      className="flex items-center gap-1.5 text-xs text-gray-600"
                    >
                      <span className={`text-${opt.color}-500`}>✓</span> {pt}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Usage quota (hosted + managed) */}
      {isHostedService && settings.smtp_choice === "managed" && usage && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            📊 Usage &amp; Quota
          </h2>
          <div className="grid grid-cols-3 gap-4 text-center">
            {[
              {
                label: "Monthly Limit",
                value: usage.quota?.monthly_limit ?? "—",
              },
              {
                label: "Emails Sent",
                value: usage.quota?.current_usage ?? "—",
              },
              { label: "Remaining", value: usage.quota?.remaining ?? "—" },
            ].map((item) => (
              <div key={item.label} className="bg-gray-50 rounded-lg p-4">
                <div className="text-2xl font-bold text-gray-800">
                  {typeof item.value === "number"
                    ? item.value.toLocaleString()
                    : item.value}
                </div>
                <div className="text-xs text-gray-500 mt-1">{item.label}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Provider + credentials (self-hosted always; hosted only when client) */}
      {showSmtpConfig && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm space-y-5">
          <h2 className="text-sm font-semibold text-gray-700">
            Email Provider
          </h2>

          {/* Provider selector */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">
              Select Provider
            </label>
            <select
              className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
              value={settings.provider || ""}
              onChange={(e) => handleProviderChange(e.target.value)}
            >
              <option value="">Choose provider…</option>
              <option value="amazonses">🟠 Amazon SES (API or SMTP)</option>
              <option value="sendgrid">SendGrid</option>
              <option value="mailgun">Mailgun</option>
              <option value="postmark">Postmark</option>
              <option value="custom">Custom SMTP</option>
            </select>
          </div>

          {/* ── Amazon SES config ── */}
          {settings.provider === "amazonses" && (
            <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 space-y-4">
              <h3 className="text-sm font-semibold text-orange-900">
                Amazon SES Configuration
              </h3>

              {/* SES mode picker */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {[
                  {
                    type: "api",
                    title: "SES API (boto3)",
                    desc: "IAM Access Key + Secret Key",
                    points: ["More features", "Better error handling"],
                  },
                  {
                    type: "smtp",
                    title: "SES SMTP",
                    desc: "SMTP username + password",
                    points: ["Standard SMTP", "Easier setup"],
                  },
                ].map((opt) => (
                  <div
                    key={opt.type}
                    onClick={() => handleSESTypeChange(opt.type)}
                    className={`p-4 border-2 rounded-xl cursor-pointer transition-all ${
                      settings.ses_type === opt.type
                        ? "border-orange-500 bg-orange-100"
                        : "border-orange-200 hover:border-orange-400 bg-white"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <input
                        type="radio"
                        readOnly
                        checked={settings.ses_type === opt.type}
                      />
                      <span className="text-sm font-semibold text-orange-900">
                        {opt.title}
                      </span>
                    </div>
                    <p className="text-xs text-orange-700 mb-2">{opt.desc}</p>
                    <ul className="space-y-0.5">
                      {opt.points.map((pt) => (
                        <li
                          key={pt}
                          className="text-xs text-orange-600 flex items-center gap-1"
                        >
                          <span>✓</span> {pt}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>

              {/* AWS Region (both modes) */}
              {settings.ses_type && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">
                    AWS Region
                  </label>
                  <select
                    className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-orange-500"
                    value={settings.aws_region || "us-east-1"}
                    onChange={(e) => handleAWSRegionChange(e.target.value)}
                  >
                    {awsRegions.map((r) => (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* SES credentials */}
              {settings.ses_type === "api" && (
                <div className="space-y-3">
                  <Field
                    label="AWS Access Key ID *"
                    value={settings.username || ""}
                    onChange={(v) =>
                      setSettings((p) => ({ ...p, username: v }))
                    }
                    placeholder="AKIAIOSFODNN7EXAMPLE"
                  />
                  <Field
                    label="AWS Secret Access Key *"
                    type="password"
                    value={settings.password || ""}
                    onChange={(v) => {
                      setPasswordEdited(true);
                      setSettings((p) => ({ ...p, password: v }));
                    }}
                    placeholder="wJalrXUtnFEMI/K7MDENG…"
                  />
                </div>
              )}

              {settings.ses_type === "smtp" && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1.5">
                      SMTP Server (auto-filled)
                    </label>
                    <input
                      type="text"
                      readOnly
                      value={settings.smtp_server}
                      className="w-full px-3 py-2.5 border rounded-lg text-sm bg-gray-50 text-gray-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1.5">
                      Port
                    </label>
                    <select
                      className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-orange-500"
                      value={settings.smtp_port || 587}
                      onChange={(e) =>
                        setSettings((p) => ({
                          ...p,
                          smtp_port: parseInt(e.target.value, 10),
                        }))
                      }
                    >
                      <option value={587}>587 (STARTTLS)</option>
                      <option value={465}>465 (SSL)</option>
                    </select>
                  </div>
                  <Field
                    label="SMTP Username *"
                    value={settings.username || ""}
                    onChange={(v) =>
                      setSettings((p) => ({ ...p, username: v }))
                    }
                    placeholder="Your SES SMTP username"
                  />
                  <Field
                    label="SMTP Password *"
                    type="password"
                    value={settings.password || ""}
                    onChange={(v) => {
                      setPasswordEdited(true);
                      setSettings((p) => ({ ...p, password: v }));
                    }}
                    placeholder="Your SES SMTP password"
                  />
                </div>
              )}

              {/* SES configuration set (optional) */}
              {settings.ses_type && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">
                    SES Configuration Set{" "}
                    <span className="text-gray-400 font-normal">
                      (optional)
                    </span>
                  </label>
                  <input
                    type="text"
                    className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-orange-500"
                    value={settings.ses_configuration_set || ""}
                    onChange={(e) =>
                      setSettings((p) => ({
                        ...p,
                        ses_configuration_set: e.target.value,
                      }))
                    }
                    placeholder="my-config-set"
                  />
                  <p className="text-xs text-gray-400 mt-1">
                    Used for SES event tracking (opens, clicks, bounces).
                  </p>
                </div>
              )}
            </div>
          )}

          {/* ── Generic SMTP provider credentials ── */}
          {settings.provider && settings.provider !== "amazonses" && (
            <div className="space-y-4">
              <p className="text-xs text-gray-500">
                {currentProviderCfg.helpText}
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">
                    SMTP Server *
                  </label>
                  <input
                    type="text"
                    className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                    value={settings.smtp_server || ""}
                    onChange={(e) =>
                      setSettings((p) => ({
                        ...p,
                        smtp_server: e.target.value,
                      }))
                    }
                    placeholder="smtp.provider.com"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">
                    Port *
                  </label>
                  <select
                    className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                    value={settings.smtp_port || 587}
                    onChange={(e) =>
                      setSettings((p) => ({
                        ...p,
                        smtp_port: parseInt(e.target.value, 10),
                      }))
                    }
                  >
                    <option value={587}>587 (STARTTLS)</option>
                    <option value={465}>465 (SSL)</option>
                    <option value={25}>25 (Plain)</option>
                    <option value={2525}>2525 (Alternative)</option>
                  </select>
                </div>
                <Field
                  label={`${currentProviderCfg.usernameLabel} *`}
                  value={settings.username || ""}
                  onChange={(v) => setSettings((p) => ({ ...p, username: v }))}
                  placeholder={currentProviderCfg.usernameLabel}
                />
                {/* FIX: password onChange sets passwordEdited flag */}
                <Field
                  label={`${currentProviderCfg.passwordLabel} *`}
                  type="password"
                  value={settings.password || ""}
                  onChange={(v) => {
                    setPasswordEdited(true);
                    setSettings((p) => ({ ...p, password: v }));
                  }}
                  placeholder={
                    settings.password === "********"
                      ? "(saved — type to change)"
                      : currentProviderCfg.passwordLabel
                  }
                />
              </div>
            </div>
          )}

          {/* Bounce forward email */}
          {settings.provider && (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">
                Bounce Forward Email{" "}
                <span className="text-gray-400 font-normal">(optional)</span>
              </label>
              <input
                type="email"
                className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                value={settings.bounce_forward_email || ""}
                onChange={(e) =>
                  setSettings((p) => ({
                    ...p,
                    bounce_forward_email: e.target.value,
                  }))
                }
                placeholder="admin@yourdomain.com"
              />
              <p className="text-xs text-gray-400 mt-1">
                Forward bounce notifications to this address.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Feedback messages */}
      <InlineMsg msg={testMsg} />
      <InlineMsg msg={saveMsg} />

      {/* Action buttons */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Test button — only when SMTP is configured */}
        {showSmtpConfig &&
          settings.provider &&
          settings.provider !== "amazonses" && (
            <button
              onClick={testConnection}
              disabled={testing || !settings.username || !settings.smtp_server}
              className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {testing ? (
                <>
                  <span className="animate-spin inline-block">↻</span> Testing…
                </>
              ) : (
                "🧪 Test Connection"
              )}
            </button>
          )}
        {showSmtpConfig &&
          settings.provider === "amazonses" &&
          settings.ses_type && (
            <button
              onClick={testConnection}
              disabled={testing || !settings.username}
              className="flex items-center gap-2 px-5 py-2.5 bg-orange-600 text-white text-sm font-semibold rounded-lg hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {testing ? (
                <>
                  <span className="animate-spin inline-block">↻</span> Testing…
                </>
              ) : (
                "🧪 Test SES Connection"
              )}
            </button>
          )}

        {/* Save button */}
        <button
          onClick={saveSettings}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-2.5 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all ml-auto"
        >
          {saving ? (
            <>
              <span className="animate-spin inline-block">↻</span> Saving…
            </>
          ) : (
            "💾 Save Configuration"
          )}
        </button>
      </div>
    </div>
  );
}

// ── Shared field component ─────────────────────────────────────────────────
function Field({ label, value, onChange, placeholder, type = "text" }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1.5">
        {label}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
      />
    </div>
  );
}

// ── Inline feedback banner ─────────────────────────────────────────────────
function InlineMsg({ msg }) {
  if (!msg) return null;
  const isSuccess = msg.type === "success";
  return (
    <div
      className={`flex items-center gap-2 px-4 py-3 rounded-lg text-sm font-medium ${
        isSuccess
          ? "bg-green-50 border border-green-200 text-green-800"
          : "bg-red-50 border border-red-200 text-red-800"
      }`}
    >
      {isSuccess ? "✓" : "✕"} {msg.text}
    </div>
  );
}
