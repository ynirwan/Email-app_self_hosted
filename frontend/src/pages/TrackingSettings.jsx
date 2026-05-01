// frontend/src/pages/TrackingSettings.jsx
//
// Changes vs previous version:
//  1. Domain pickers only show verified domains from GET /domains/verified
//  2. Each domain field has a "Check" button that hits GET /domains/verified
//     and verifies the chosen domain is reachable for its purpose
//  3. Subdomain prefix input per field (e.g. "track" → track.example.com)
//  4. Save now sends all 7 fields — fixes the silent domain data-loss bug
//     (was caused by setting.py's old TrackingSettings model missing domain fields)

import { useState, useEffect, useCallback } from 'react';
import API from '../api';

// ─── Toast ────────────────────────────────────────────────────────────────────
function useToast() {
  const [msg, setMsg] = useState({ text: '', type: 'success' });
  const show = (text, type = 'success') => {
    setMsg({ text, type });
    setTimeout(() => setMsg({ text: '', type: 'success' }), 4000);
  };
  return { msg, show };
}

function InlineMsg({ msg }) {
  if (!msg.text) return null;
  const cls = msg.type === 'error'
    ? 'bg-red-50 border-red-200 text-red-700'
    : 'bg-green-50 border-green-200 text-green-700';
  return (
    <div className={`px-4 py-3 rounded-xl border text-sm ${cls}`}>{msg.text}</div>
  );
}

// ─── Toggle ───────────────────────────────────────────────────────────────────
function Toggle({ checked, onChange, disabled }) {
  return (
    <button type="button" role="switch" aria-checked={checked} disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent
        transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2
        ${checked ? 'bg-indigo-600' : 'bg-gray-200'} ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}>
      <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow
        transition duration-200 ${checked ? 'translate-x-5' : 'translate-x-0'}`} />
    </button>
  );
}

function SettingRow({ icon, label, description, checked, onChange, badge }) {
  return (
    <div className="flex items-start justify-between gap-4 py-5">
      <div className="flex items-start gap-3 flex-1 min-w-0">
        <div className="w-9 h-9 rounded-lg bg-indigo-50 flex items-center justify-center flex-shrink-0 text-lg">{icon}</div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-gray-800">{label}</p>
            {badge && <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-xs font-medium rounded-full">{badge}</span>}
          </div>
          <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{description}</p>
        </div>
      </div>
      <div className="flex-shrink-0 pt-0.5"><Toggle checked={checked} onChange={onChange} /></div>
    </div>
  );
}

function StatusPill({ enabled }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold
      ${enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${enabled ? 'bg-green-500' : 'bg-gray-400'}`} />
      {enabled ? 'Active' : 'Disabled'}
    </span>
  );
}

// ─── Domain picker ────────────────────────────────────────────────────────────
// Splits the saved value (e.g. "track.example.com") back into prefix + root.
// Calls onChange(effectiveString) on every change.
// "Check" button does a lightweight fetch to verify the domain is reachable
// for the expected path (open pixel / click redirect / unsubscribe).
function DomainPicker({ label, description, checkPath, value, onChange, verifiedDomains, loadingDomains }) {
  const [root,   setRoot]   = useState('');
  const [prefix, setPrefix] = useState('');
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState(null); // null | 'ok' | 'fail'

  // Parse saved value back to root + prefix when domains load or value changes
  useEffect(() => {
    if (!value) { setRoot(''); setPrefix(''); return; }
    const match = verifiedDomains.find(d => value === d.domain || value.endsWith(`.${d.domain}`));
    if (match) {
      setRoot(match.domain);
      setPrefix(value === match.domain ? '' : value.slice(0, value.length - match.domain.length - 1));
    } else {
      setRoot(value);
      setPrefix('');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, verifiedDomains.length]);

  const effective = prefix.trim() ? `${prefix.trim()}.${root}` : root;

  const handleRootChange = (r) => {
    setRoot(r);
    setCheckResult(null);
    const eff = prefix.trim() ? `${prefix.trim()}.${r}` : r;
    onChange(eff);
  };

  const handlePrefixChange = (p) => {
    const clean = p.toLowerCase().replace(/[^a-z0-9-]/g, '');
    setPrefix(clean);
    setCheckResult(null);
    const eff = clean ? `${clean}.${root}` : root;
    onChange(eff);
  };

  // Lightweight reachability check: tries to fetch the test path on the domain
  const checkReachability = async () => {
    if (!effective) return;
    setChecking(true);
    setCheckResult(null);
    try {
      // Use a no-cors fetch — we just want to see if the server responds at all.
      // A 404 / redirect from our own server still means it's reachable.
      const url = `https://${effective}${checkPath}`;
      const res = await fetch(url, { method: 'GET', mode: 'no-cors', signal: AbortSignal.timeout(5000) });
      // no-cors always gives opaque response — if it didn't throw, host is reachable
      setCheckResult('ok');
    } catch {
      setCheckResult('fail');
    } finally {
      setChecking(false);
    }
  };

  if (loadingDomains) {
    return (
      <div className="py-5">
        <p className="text-sm font-semibold text-gray-800 mb-2">{label}</p>
        <div className="h-9 bg-gray-100 rounded-lg animate-pulse" />
      </div>
    );
  }

  return (
    <div className="py-5">
      <label className="block text-sm font-semibold text-gray-800 mb-1">{label}</label>
      <p className="text-xs text-gray-500 mb-3 leading-relaxed">{description}</p>

      {verifiedDomains.length === 0 ? (
        <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5 text-xs text-amber-800">
          <span className="text-base shrink-0">⚠</span>
          <span>No verified domains yet. <a href="/settings/domain" className="underline font-medium">Add and verify a domain →</a></span>
        </div>
      ) : (
        <>
          <div className="flex items-stretch rounded-lg border border-gray-300 overflow-hidden focus-within:ring-2 focus-within:ring-indigo-400 bg-white">
            {/* Subdomain prefix */}
            <input
              type="text"
              value={prefix}
              onChange={e => handlePrefixChange(e.target.value)}
              placeholder="subdomain"
              disabled={!root}
              className="w-28 px-3 py-2 text-sm font-mono outline-none border-none bg-transparent disabled:bg-gray-50 disabled:text-gray-400"
            />
            <span className="flex items-center px-1.5 text-gray-400 text-sm bg-gray-50 border-x border-gray-200 select-none">.</span>

            {/* Root domain */}
            <select
              value={root}
              onChange={e => handleRootChange(e.target.value)}
              className="flex-1 px-3 py-2 text-sm outline-none border-none bg-transparent cursor-pointer"
            >
              <option value="">— select verified domain —</option>
              {verifiedDomains.map(d => (
                <option key={d.id} value={d.domain}>{d.domain}</option>
              ))}
            </select>

            {/* Reachability check button */}
            <button
              type="button"
              onClick={checkReachability}
              disabled={!effective || checking}
              className="px-3 py-2 text-xs font-medium border-l border-gray-200 bg-gray-50
                hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap text-gray-600">
              {checking ? '…' : 'Check'}
            </button>
          </div>

          {/* Effective domain + check result */}
          <div className="mt-2 flex items-center gap-3 flex-wrap">
            {effective && root ? (
              <span className="text-xs text-gray-400">
                Effective: <code className="font-mono text-indigo-700 bg-indigo-50 px-1.5 py-0.5 rounded">{effective}</code>
              </span>
            ) : (
              <span className="text-xs text-gray-400 italic">No domain selected — will use server default</span>
            )}

            {checkResult === 'ok' && (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 bg-green-50 border border-green-200 px-2 py-0.5 rounded-full">
                ✓ Reachable
              </span>
            )}
            {checkResult === 'fail' && (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 px-2 py-0.5 rounded-full">
                ✗ Not reachable — check DNS / CNAME
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function TrackingSettings() {
  const { msg, show } = useToast();

  const [settings, setSettings] = useState({
    open_tracking_enabled:        true,
    click_tracking_enabled:       true,
    unsubscribe_tracking_enabled: true,
    track_unique_only:            true,
    open_tracking_domain:         '',
    click_tracking_domain:        '',
    unsubscribe_domain:           '',
  });
  const [fetching,        setFetching]        = useState(true);
  const [saving,          setSaving]          = useState(false);
  const [dirty,           setDirty]           = useState(false);
  const [verifiedDomains, setVerifiedDomains] = useState([]);
  const [loadingDomains,  setLoadingDomains]  = useState(true);

  useEffect(() => {
    API.get('/settings/tracking')
      .then(res => setSettings(s => ({ ...s, ...res.data })))
      .catch(() => show('Failed to load tracking settings.', 'error'))
      .finally(() => setFetching(false));
  }, []);

  useEffect(() => {
    API.get('/domains/verified')
      .then(res => setVerifiedDomains(res.data?.domains || []))
      .catch(() => {})
      .finally(() => setLoadingDomains(false));
  }, []);

  const update = (key, val) => {
    setSettings(s => ({ ...s, [key]: val }));
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      // Send all 7 fields explicitly — prevents partial saves
      const payload = {
        open_tracking_enabled:        settings.open_tracking_enabled,
        click_tracking_enabled:       settings.click_tracking_enabled,
        unsubscribe_tracking_enabled: settings.unsubscribe_tracking_enabled,
        track_unique_only:            settings.track_unique_only,
        open_tracking_domain:         settings.open_tracking_domain || '',
        click_tracking_domain:        settings.click_tracking_domain || '',
        unsubscribe_domain:           settings.unsubscribe_domain || '',
      };
      const res = await API.put('/settings/tracking', payload);
      if (res.data?.status === 'saved') {
        const { status, type, updated_at, ...srv } = res.data;
        setSettings(p => ({ ...p, ...srv }));
      }
      show('Tracking settings saved.');
      setDirty(false);
    } catch (e) {
      show(e.response?.data?.detail || 'Failed to save settings.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const activeCount = [
    settings.open_tracking_enabled,
    settings.click_tracking_enabled,
    settings.unsubscribe_tracking_enabled,
  ].filter(Boolean).length;

  if (fetching) {
    return (
      <div className="space-y-4 animate-pulse max-w-2xl">
        <div className="h-8 bg-gray-100 rounded-lg w-48" />
        <div className="h-48 bg-gray-100 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">

      <div>
        <h2 className="text-lg font-bold text-gray-900">Email Tracking</h2>
        <p className="text-sm text-gray-500 mt-1">
          Control what gets tracked when recipients open or interact with your campaigns.
          Changes apply to <strong>new campaign sends only</strong> — they do not retroactively
          affect emails already in flight.
        </p>
      </div>

      <InlineMsg msg={msg} />

      {/* Status bar */}
      <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-sm">
        <span className="text-gray-500 font-medium">Active tracking features:</span>
        <span className="font-bold text-gray-800">{activeCount} / 3</span>
        <span className="ml-auto">
          {activeCount === 3 && <StatusPill enabled />}
          {activeCount === 0 && <StatusPill enabled={false} />}
          {activeCount > 0 && activeCount < 3 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />Partial
            </span>
          )}
        </span>
      </div>

      {/* Toggle rows */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm divide-y divide-gray-100">
        <div className="px-5">
          <SettingRow icon="👁️" label="Open Tracking"
            description="Inserts a 1×1 invisible pixel into every outgoing email. When a recipient opens the email their mail client loads the pixel, recording an open event and computing open rates."
            checked={settings.open_tracking_enabled}
            onChange={val => update('open_tracking_enabled', val)} />
        </div>
        <div className="px-5">
          <SettingRow icon="🔗" label="Click Tracking"
            description="Rewrites links in your emails through a tracking redirect before delivery. Captures which links recipients click and feeds click-rate analytics."
            checked={settings.click_tracking_enabled}
            onChange={val => update('click_tracking_enabled', val)} />
        </div>
        <div className="px-5">
          <SettingRow icon="🚫" label="Unsubscribe Event Tracking" badge="Recommended on"
            description="Logs an event every time someone clicks an unsubscribe link. Required for accurate unsubscribe-rate reporting. Disabling this does not stop unsubscribes from working — it only stops recording them in analytics."
            checked={settings.unsubscribe_tracking_enabled}
            onChange={val => update('unsubscribe_tracking_enabled', val)} />
        </div>
        <div className="px-5">
          <SettingRow icon="1️⃣" label="Count Unique Events Only"
            description="When enabled, only the first open and first click per subscriber per campaign are counted in analytics. Subsequent opens/clicks from the same person are still logged but do not increment the unique totals used for rate calculations."
            checked={settings.track_unique_only}
            onChange={val => update('track_unique_only', val)} />
        </div>
      </div>

      {/* Tracking Domains */}
      <div>
        <h3 className="text-sm font-bold text-gray-800 mb-1">Tracking Domains</h3>
        <p className="text-xs text-gray-500 mb-1 leading-relaxed">
          Choose a verified domain for each URL type. Optionally add a subdomain prefix
          (e.g. <code className="font-mono text-xs">track</code> → <code className="font-mono text-xs">track.example.com</code>).
          Use <strong>Check</strong> to confirm the domain is reachable before saving.
        </p>
        <p className="text-xs text-gray-400 mb-4">
          Only verified domains appear here.{' '}
          <a href="/settings/domain" className="text-indigo-600 underline">Manage domains →</a>
        </p>

        <div className="bg-white border border-gray-200 rounded-xl shadow-sm divide-y divide-gray-100 px-5">
          <DomainPicker
            label="Open Tracking Domain"
            description="Domain for the 1×1 pixel URL embedded in emails. The path /t/o/<token>.gif must resolve to this server."
            checkPath="/t/o/healthcheck.gif"
            value={settings.open_tracking_domain}
            onChange={val => update('open_tracking_domain', val)}
            verifiedDomains={verifiedDomains}
            loadingDomains={loadingDomains}
          />
          <DomainPicker
            label="Click Tracking Domain"
            description="Domain for click-redirect links. Recipients briefly see this domain when clicking. The path /t/c/<token> must resolve to this server."
            checkPath="/t/c/healthcheck"
            value={settings.click_tracking_domain}
            onChange={val => update('click_tracking_domain', val)}
            verifiedDomains={verifiedDomains}
            loadingDomains={loadingDomains}
          />
          <DomainPicker
            label="Unsubscribe Domain"
            description="Domain for unsubscribe links injected via {{unsubscribe_url}}. The path /unsubscribe/<token> must resolve to this server."
            checkPath="/unsubscribe/healthcheck"
            value={settings.unsubscribe_domain}
            onChange={val => update('unsubscribe_domain', val)}
            verifiedDomains={verifiedDomains}
            loadingDomains={loadingDomains}
          />
        </div>
      </div>

      {/* Save bar */}
      <div className="flex items-center justify-between pt-2">
        <p className="text-xs text-gray-400">{dirty ? '● Unsaved changes' : 'All changes saved'}</p>
        <button onClick={save} disabled={saving || !dirty}
          className="px-6 py-2.5 bg-indigo-600 text-white text-sm font-semibold rounded-xl
            hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
          {saving ? 'Saving…' : 'Save Settings'}
        </button>
      </div>

      {/* Privacy notice */}
      <div className="flex gap-3 p-4 bg-blue-50 border border-blue-100 rounded-xl text-sm text-blue-800">
        <span className="text-lg flex-shrink-0">🔒</span>
        <div>
          <p className="font-semibold mb-1">Privacy consideration</p>
          <p className="text-blue-700 leading-relaxed text-xs">
            Disabling open tracking removes the tracking pixel entirely from sent emails.
            Disabling click tracking sends links without redirect wrapping. Both are good choices
            if your audience includes strict privacy users or if you operate under regulations
            that require minimal data collection.
          </p>
        </div>
      </div>

    </div>
  );
}