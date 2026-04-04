import { useState, useEffect, useCallback } from 'react';
import API from '../api';

// ── shared helpers (same pattern as DomainSettings) ───────────────────────────
function useToast() {
  const [msg, setMsg] = useState(null);
  const show = useCallback((text, type = 'info') => {
    setMsg({ text, type });
    setTimeout(() => setMsg(null), 4000);
  }, []);
  return { msg, show };
}

function InlineMsg({ msg }) {
  if (!msg) return null;
  const styles = {
    success: 'bg-green-50 border-green-200 text-green-800',
    error:   'bg-red-50   border-red-200   text-red-800',
    info:    'bg-blue-50  border-blue-200  text-blue-800',
  };
  const icons = { success: '✓', error: '✕', info: 'ℹ' };
  return (
    <div className={`flex items-center gap-2 px-4 py-3 rounded-lg text-sm font-medium border ${styles[msg.type]}`}>
      <span>{icons[msg.type]}</span> {msg.text}
    </div>
  );
}

// ── Toggle switch ─────────────────────────────────────────────────────────────
function Toggle({ checked, onChange, disabled }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent
        transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2
        ${checked ? 'bg-indigo-600' : 'bg-gray-200'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      <span
        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0
          transition duration-200 ease-in-out
          ${checked ? 'translate-x-5' : 'translate-x-0'}`}
      />
    </button>
  );
}

// ── Setting row ───────────────────────────────────────────────────────────────
function SettingRow({ icon, label, description, checked, onChange, disabled, badge }) {
  return (
    <div className={`flex items-start justify-between gap-4 py-5 ${disabled ? 'opacity-60' : ''}`}>
      <div className="flex items-start gap-3 flex-1 min-w-0">
        <div className="w-9 h-9 rounded-lg bg-indigo-50 flex items-center justify-center flex-shrink-0 text-lg">
          {icon}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-gray-800">{label}</p>
            {badge && (
              <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-xs font-medium rounded-full">
                {badge}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{description}</p>
        </div>
      </div>
      <div className="flex-shrink-0 pt-0.5">
        <Toggle checked={checked} onChange={onChange} disabled={disabled} />
      </div>
    </div>
  );
}

// ── Status pill ───────────────────────────────────────────────────────────────
function StatusPill({ enabled }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold
      ${enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${enabled ? 'bg-green-500' : 'bg-gray-400'}`} />
      {enabled ? 'Active' : 'Disabled'}
    </span>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function TrackingSettings() {
  const { msg, show } = useToast();

  const [settings, setSettings] = useState({
    open_tracking_enabled:         true,
    click_tracking_enabled:        true,
    unsubscribe_tracking_enabled:  true,
    track_unique_only:             true,
  });
  const [loading, setSaving_] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [dirty, setDirty] = useState(false);

  // ── Load ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const res = await API.get('/settings/tracking');
        setSettings(res.data);
      } catch {
        show('Failed to load tracking settings.', 'error');
      } finally {
        setFetching(false);
      }
    })();
  }, []);

  const update = (key, val) => {
    setSettings(s => ({ ...s, [key]: val }));
    setDirty(true);
  };

  // ── Save ──────────────────────────────────────────────────────────────────
  const save = async () => {
    setSaving_(true);
    try {
      await API.put('/settings/tracking', settings);
      show('Tracking settings saved.', 'success');
      setDirty(false);
    } catch (e) {
      show(e.response?.data?.detail || 'Failed to save settings.', 'error');
    } finally {
      setSaving_(false);
    }
  };

  // ── How many features active ──────────────────────────────────────────────
  const activeCount = [
    settings.open_tracking_enabled,
    settings.click_tracking_enabled,
    settings.unsubscribe_tracking_enabled,
  ].filter(Boolean).length;

  if (fetching) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-8 bg-gray-100 rounded-lg w-48" />
        <div className="h-48 bg-gray-100 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">

      {/* ── Header ── */}
      <div>
        <h2 className="text-lg font-bold text-gray-900">Email Tracking</h2>
        <p className="text-sm text-gray-500 mt-1">
          Control what gets tracked when recipients open or interact with your campaigns.
          Changes apply to <strong>new campaign sends only</strong> — they do not retroactively
          affect emails already in flight.
        </p>
      </div>

      <InlineMsg msg={msg} />

      {/* ── Status summary bar ── */}
      <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-sm">
        <span className="text-gray-500 font-medium">Active tracking features:</span>
        <span className="font-bold text-gray-800">{activeCount} / 3</span>
        <span className="ml-auto">
          {activeCount === 3 && <StatusPill enabled />}
          {activeCount === 0 && <StatusPill enabled={false} />}
          {activeCount > 0 && activeCount < 3 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              Partial
            </span>
          )}
        </span>
      </div>

      {/* ── Toggle rows ── */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm divide-y divide-gray-100">

        <div className="px-5">
          <SettingRow
            icon="👁️"
            label="Open Tracking"
            description={
              `Inserts a 1×1 invisible pixel into every outgoing email. When a recipient opens the email
              their mail client loads the pixel, recording an open event and computing open rates.`
            }
            checked={settings.open_tracking_enabled}
            onChange={val => update('open_tracking_enabled', val)}
          />
        </div>

        <div className="px-5">
          <SettingRow
            icon="🔗"
            label="Click Tracking"
            description={
              `Rewrites links in your emails through a tracking redirect before delivery.
              Captures which links recipients click and feeds click-rate analytics.`
            }
            checked={settings.click_tracking_enabled}
            onChange={val => update('click_tracking_enabled', val)}
          />
        </div>

        <div className="px-5">
          <SettingRow
            icon="🚫"
            label="Unsubscribe Event Tracking"
            description={
              `Logs an event every time someone clicks an unsubscribe link. Required for accurate
              unsubscribe-rate reporting. Disabling this does not stop unsubscribes from working —
              it only stops recording them in analytics.`
            }
            badge="Recommended on"
            checked={settings.unsubscribe_tracking_enabled}
            onChange={val => update('unsubscribe_tracking_enabled', val)}
          />
        </div>

        <div className="px-5">
          <SettingRow
            icon="1️⃣"
            label="Count Unique Events Only"
            description={
              `When enabled, only the first open and first click per subscriber per campaign are
              counted in analytics. Subsequent opens/clicks from the same person are still logged
              but do not increment the unique totals used for rate calculations.`
            }
            checked={settings.track_unique_only}
            onChange={val => update('track_unique_only', val)}
          />
        </div>
      </div>

      {/* ── Privacy notice ── */}
      <div className="flex gap-3 p-4 bg-blue-50 border border-blue-100 rounded-xl text-sm text-blue-800">
        <span className="text-lg flex-shrink-0">🔒</span>
        <div>
          <p className="font-semibold mb-1">Privacy consideration</p>
          <p className="text-blue-700 leading-relaxed">
            Disabling open tracking removes the tracking pixel entirely from sent emails.
            Disabling click tracking sends links without redirect wrapping. Both are good
            choices if your audience includes strict privacy users or if you operate under
            regulations that require minimal data collection.
          </p>
        </div>
      </div>

      {/* ── What happens on disable callout ── */}
      {(!settings.open_tracking_enabled || !settings.click_tracking_enabled) && (
        <div className="flex gap-3 p-4 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-800">
          <span className="text-lg flex-shrink-0">⚠️</span>
          <div>
            <p className="font-semibold mb-1">Heads up</p>
            <ul className="list-disc list-inside space-y-1 text-amber-700">
              {!settings.open_tracking_enabled && (
                <li>Open rates will show <strong>0 opens</strong> for new campaigns — this is expected.</li>
              )}
              {!settings.click_tracking_enabled && (
                <li>Click rates will show <strong>0 clicks</strong> for new campaigns — links go directly to the destination.</li>
              )}
            </ul>
          </div>
        </div>
      )}

      {/* ── Save button ── */}
      <div className="flex items-center gap-3 pt-1">
        <button
          onClick={save}
          disabled={loading || !dirty}
          className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-all
            ${dirty
              ? 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm'
              : 'bg-gray-100 text-gray-400 cursor-not-allowed'
            }
            ${loading ? 'opacity-70' : ''}`}
        >
          {loading ? 'Saving…' : dirty ? 'Save Changes' : 'Saved'}
        </button>
        {dirty && (
          <p className="text-xs text-amber-600 font-medium">Unsaved changes</p>
        )}
      </div>
    </div>
  );
}