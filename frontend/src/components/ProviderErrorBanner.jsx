// frontend/src/components/ProviderErrorBanner.jsx
// Shared between CampaignAnalytics, EditCampaign, and ABTestResults.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import API from "../api";

const ERROR_TYPE_LABELS = {
  auth_failed:           "Auth Failed",
  sender_not_authorized: "Sender Not Authorized",
  domain_not_verified:   "Domain Not Verified",
  bad_sender_format:     "Bad Sender Format",
  account_suspended:     "Account Suspended",
  tls_required:          "TLS Required",
  connection_refused:    "Connection Refused",
  no_provider:           "No Provider Configured",
  daily_quota_exceeded:  "Daily Quota Exceeded",
  rate_limited:          "Rate Limited",
  hourly_limit:          "Hourly Limit Reached",
  service_unavailable:   "Service Unavailable",
  local_error:           "Provider Local Error",
  connection_timeout:    "Connection Timeout",
  unknown_error:         "Unknown Error",
};

// These error types expose a sender fix form
const SENDER_FIX_TYPES = new Set([
  "sender_not_authorized",
  "auth_failed",
  "bad_sender_format",
]);

export default function ProviderErrorBanner({
  providerError,
  isCampaign = false,   // true = campaigns (fix form + resume); false = A/B tests (terminal)
  campaignId,
  onFixed,              // callback after successful sender save
  onResumed,            // callback after resume
}) {
  const navigate = useNavigate();

  const [senderName,  setSenderName]  = useState("");
  const [senderEmail, setSenderEmail] = useState("");
  const [saving,   setSaving]   = useState(false);
  const [resuming, setResuming] = useState(false);
  const [saveMsg,  setSaveMsg]  = useState("");
  const [saveErr,  setSaveErr]  = useState("");
  const [fixed,    setFixed]    = useState(false);
  const [showRaw,  setShowRaw]  = useState(false);

  if (!providerError) return null;

  const {
    error_class,
    error_type,
    human_message,
    raw_message,
    smtp_code,
    is_resumable,
    detected_at,
  } = providerError;

  const isConfigError = error_class === "config_error";
  const showFixForm   = isCampaign && isConfigError && SENDER_FIX_TYPES.has(error_type);
  const showResume    = isCampaign && (is_resumable || fixed);

  const borderCls = isConfigError
    ? "border-red-300 bg-red-50"
    : "border-amber-300 bg-amber-50";
  const badgeCls  = isConfigError
    ? "bg-red-100 text-red-700 border border-red-300"
    : "bg-amber-100 text-amber-700 border border-amber-300";

  const handleSaveSender = async () => {
    setSaveErr("");
    setSaveMsg("");
    if (!senderEmail.trim()) {
      setSaveErr("Sender email is required");
      return;
    }
    setSaving(true);
    try {
      // Fetch current campaign to merge non-sender fields
      const res = await API.get(`/campaigns/${campaignId}`);
      const current = res.data;
      await API.put(`/campaigns/${campaignId}`, {
        ...current,
        sender_name:  senderName || current.sender_name,
        sender_email: senderEmail,
      });
      setSaveMsg("Sender updated. You can now resume the campaign.");
      setFixed(true);
      onFixed && onFixed();
    } catch (err) {
      setSaveErr(err.response?.data?.detail || "Failed to save sender settings");
    } finally {
      setSaving(false);
    }
  };

  const handleResume = async () => {
    setResuming(true);
    setSaveErr("");
    try {
      await API.post(`/campaigns/${campaignId}/resume`);
      onResumed && onResumed();
    } catch (err) {
      setSaveErr(err.response?.data?.detail || "Failed to resume campaign");
    } finally {
      setResuming(false);
    }
  };

  return (
    <div className={`rounded-xl border-2 p-5 mb-6 ${borderCls}`}>
      <div className="flex items-start gap-3">
        <span className="text-2xl flex-shrink-0">⚠️</span>

        <div className="flex-1 min-w-0">
          {/* Title + type badge */}
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="font-bold text-gray-900 text-sm">
              {isCampaign
                ? "Campaign auto-paused due to provider error"
                : "A/B test failed due to provider error"}
            </span>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${badgeCls}`}>
              {ERROR_TYPE_LABELS[error_type] || error_type}
            </span>
          </div>

          {/* Human-readable message */}
          <p className="text-sm text-gray-800 mb-3">{human_message}</p>

          {/* Collapsible raw detail */}
          <details onToggle={(e) => setShowRaw(e.target.open)} className="text-xs mb-3">
            <summary className="cursor-pointer text-gray-500 hover:text-gray-700 select-none">
              {showRaw ? "▾" : "▸"} Technical details
            </summary>
            <div className="bg-white/70 rounded-lg border border-gray-200 p-3 font-mono mt-1 space-y-1">
              {smtp_code && <p><span className="text-gray-500">SMTP code:</span> {smtp_code}</p>}
              <p className="break-all"><span className="text-gray-500">Raw error:</span> {raw_message || "—"}</p>
              {detected_at && (
                <p><span className="text-gray-500">Detected:</span> {new Date(detected_at).toLocaleString()}</p>
              )}
            </div>
          </details>

          {/* Inline fix form — campaigns with fixable sender errors */}
          {showFixForm && !fixed && (
            <div className="mt-2 bg-white/80 rounded-lg border border-gray-200 p-4 mb-3">
              <p className="text-sm font-semibold text-gray-800 mb-3">Fix sender details</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Sender Name</label>
                  <input
                    type="text"
                    value={senderName}
                    onChange={(e) => setSenderName(e.target.value)}
                    placeholder="Your Name / Company"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Sender Email *</label>
                  <input
                    type="email"
                    value={senderEmail}
                    onChange={(e) => setSenderEmail(e.target.value)}
                    placeholder="you@yourdomain.com"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
              <button
                onClick={handleSaveSender}
                disabled={saving}
                className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-60"
              >
                {saving ? "Saving…" : "Save Sender Settings"}
              </button>
            </div>
          )}

          {/* Save feedback */}
          {saveMsg && <p className="text-sm text-green-700 font-medium mb-2">✓ {saveMsg}</p>}
          {saveErr && <p className="text-sm text-red-600 mb-2">{saveErr}</p>}

          {/* Resume button */}
          {showResume && (
            <div className="mb-3">
              <button
                onClick={handleResume}
                disabled={resuming}
                className="px-4 py-2 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 disabled:opacity-60"
              >
                {resuming ? "Resuming…" : "▶ Resume Campaign"}
              </button>
            </div>
          )}

          {/* Footer links */}
          <div className="pt-3 border-t border-gray-200/70 flex flex-wrap gap-4 text-sm">
            <button
              onClick={() => navigate("/settings/email")}
              className="text-blue-600 hover:underline"
            >
              Check your email settings →
            </button>
            {!isCampaign && (
              <span className="text-gray-600 text-xs">
                Fix your email settings and create a new A/B test.
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}