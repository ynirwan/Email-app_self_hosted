// frontend/src/pages/LicenseSettings.jsx
//
// License management panel — shows current license status and lets an admin
// upload a new .lic / .json license file without restarting the server.
//
// Two actions:
//   1. Upload file   → POST /api/license/upload  (validates + writes + reloads)
//   2. Reload        → POST /api/license/reload   (re-reads from disk, no file needed)

import { useState, useRef, useCallback } from "react";
import API from "../api";
import { useLicense } from "../contexts/LicenseContext";

// ── helpers ──────────────────────────────────────────────────────────────────

function planBadgeClass(plan) {
  switch (plan) {
    case "enterprise": return "bg-purple-100 text-purple-800";
    case "professional": return "bg-blue-100 text-blue-800";
    default: return "bg-gray-100 text-gray-700";
  }
}

function planLabel(plan) {
  switch (plan) {
    case "enterprise":    return "Enterprise";
    case "professional":  return "Professional";
    default:              return "Starter";
  }
}

function ExpiryBadge({ daysUntilExpiry, isExpired, expiresAt }) {
  if (!expiresAt) return null;
  if (isExpired)
    return <span className="text-xs font-medium text-red-600 bg-red-50 px-2 py-0.5 rounded">Expired</span>;
  if (daysUntilExpiry <= 30)
    return (
      <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded">
        Expires in {daysUntilExpiry}d
      </span>
    );
  return (
    <span className="text-xs text-gray-500">
      Expires {new Date(expiresAt).toLocaleDateString()}
    </span>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function LicenseSettings() {
  const { license, refetchLicense } = useLicense();

  const [dragging, setDragging]   = useState(false);
  const [uploading, setUploading] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [result, setResult]       = useState(null); // { ok: bool, message: string }

  const fileInputRef = useRef(null);

  // ── upload ────────────────────────────────────────────────────────────────

  const uploadFile = useCallback(async (file) => {
    if (!file) return;

    const ext = file.name.split(".").pop().toLowerCase();
    if (ext !== "lic" && ext !== "json") {
      setResult({ ok: false, message: "Only .lic or .json license files are accepted." });
      return;
    }

    const form = new FormData();
    form.append("file", file);

    setUploading(true);
    setResult(null);

    try {
      const res = await API.post("/license/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const d = res.data;
      setResult({
        ok: d.valid,
        message: d.valid
          ? `License activated — ${planLabel(d.plan)} plan, expires ${d.expires_at ?? "never"}.`
          : `File saved but license is invalid: ${d.error ?? "unknown error"}`,
      });
      await refetchLicense();
    } catch (err) {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        "Upload failed — check the server logs.";
      setResult({ ok: false, message: detail });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [refetchLicense]);

  // ── reload ────────────────────────────────────────────────────────────────

  const reloadLicense = useCallback(async () => {
    setReloading(true);
    setResult(null);
    try {
      const res = await API.post("/license/reload");
      const d = res.data;
      setResult({
        ok: d.valid,
        message: d.valid
          ? `License reloaded — ${planLabel(d.plan)} plan.`
          : `Reload failed: ${d.error ?? "unknown error"}`,
      });
      await refetchLicense();
    } catch (err) {
      setResult({ ok: false, message: err?.response?.data?.detail ?? "Reload failed." });
    } finally {
      setReloading(false);
    }
  }, [refetchLicense]);

  // ── drag-drop handlers ────────────────────────────────────────────────────

  const onDragOver  = (e) => { e.preventDefault(); setDragging(true);  };
  const onDragLeave = ()  => { setDragging(false); };
  const onDrop      = (e) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) uploadFile(file);
  };

  // ── render ────────────────────────────────────────────────────────────────

  const lic = license;

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">License</h2>
        <p className="text-sm text-gray-500 mt-1">
          Upload a new license file at any time — no server restart required.
        </p>
      </div>

      {/* ── Current status card ── */}
      <div className="border border-gray-200 rounded-lg p-5 bg-white space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-700">Current license</h3>
          {!lic.loading && (
            <span
              className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                lic.valid ? planBadgeClass(lic.plan) : "bg-red-100 text-red-700"
              }`}
            >
              {lic.valid ? planLabel(lic.plan) : "Invalid"}
            </span>
          )}
        </div>

        {lic.loading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : lic.valid ? (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            {lic.issuedTo && (
              <>
                <dt className="text-gray-500">Issued to</dt>
                <dd className="text-gray-900 font-medium">{lic.issuedTo}</dd>
              </>
            )}
            {lic.domain && (
              <>
                <dt className="text-gray-500">Domain</dt>
                <dd className="text-gray-900 font-mono text-xs">{lic.domain}</dd>
              </>
            )}
            <dt className="text-gray-500">Expiry</dt>
            <dd>
              <ExpiryBadge
                daysUntilExpiry={lic.daysUntilExpiry}
                isExpired={lic.isExpired}
                expiresAt={lic.expiresAt}
              />
            </dd>
          </dl>
        ) : (
          <div className="flex items-start gap-2 text-sm text-red-600 bg-red-50 rounded p-3">
            <span className="mt-0.5">⚠</span>
            <span>{lic.error ?? "No valid license loaded."}</span>
          </div>
        )}

        {/* reload button */}
        <div className="pt-1">
          <button
            onClick={reloadLicense}
            disabled={reloading}
            className="text-xs text-blue-600 hover:text-blue-800 disabled:opacity-50"
          >
            {reloading ? "Reloading…" : "↻ Reload from disk"}
          </button>
          <span className="text-xs text-gray-400 ml-2">
            (if you placed a file on the server manually)
          </span>
        </div>
      </div>

      {/* ── Upload zone ── */}
      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer ${
          dragging
            ? "border-blue-500 bg-blue-50"
            : "border-gray-300 hover:border-blue-400 bg-gray-50"
        }`}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".lic,.json"
          className="hidden"
          onChange={(e) => uploadFile(e.target.files?.[0])}
        />

        {uploading ? (
          <p className="text-sm text-blue-600 font-medium">Uploading and validating…</p>
        ) : (
          <>
            <p className="text-sm font-medium text-gray-700">
              Drop your license file here, or <span className="text-blue-600">browse</span>
            </p>
            <p className="text-xs text-gray-400 mt-1">Accepts .lic or .json — validated before saving</p>
          </>
        )}
      </div>

      {/* ── Result banner ── */}
      {result && (
        <div
          className={`flex items-start gap-2 rounded-lg p-3 text-sm ${
            result.ok
              ? "bg-green-50 text-green-800 border border-green-200"
              : "bg-red-50 text-red-700 border border-red-200"
          }`}
        >
          <span className="mt-0.5 shrink-0">{result.ok ? "✓" : "✗"}</span>
          <span>{result.message}</span>
          <button
            onClick={() => setResult(null)}
            className="ml-auto shrink-0 text-gray-400 hover:text-gray-600"
          >
            ×
          </button>
        </div>
      )}

      {/* ── Feature summary ── */}
      {!lic.loading && lic.valid && Object.keys(lic.features).length > 0 && (
        <div className="border border-gray-200 rounded-lg p-5 bg-white">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Enabled features</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(lic.features)
              .filter(([, v]) => v === true || (typeof v === "number" && v !== 0))
              .map(([k]) => (
                <span
                  key={k}
                  className="text-xs bg-green-50 text-green-700 border border-green-200 px-2 py-0.5 rounded"
                >
                  {k.replace(/_/g, " ")}
                </span>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
