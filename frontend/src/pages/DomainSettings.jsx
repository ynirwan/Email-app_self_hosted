// frontend/src/pages/DomainSettings.jsx
//
// Single page for:
//   Section 1 — Domain management (add, verify, A/CNAME records after verify)
//   Section 2 — Tracking settings (toggles + domain pickers + save)
//
// TrackingSettings.jsx is no longer needed.

import { useState, useEffect, useCallback } from 'react';
import { useSettings } from "../contexts/SettingsContext";
import API from '../api';

// ─── Shared helpers ───────────────────────────────────────────────────────────

function Toast({ msg, type, onDismiss }) {
  if (!msg) return null;
  const cls = type === 'error'
    ? 'bg-red-50 border-red-200 text-red-700'
    : 'bg-green-50 border-green-200 text-green-700';
  return (
    <div className={`flex items-center justify-between px-4 py-3 rounded-xl border text-sm ${cls}`}>
      <span>{msg}</span>
      <button onClick={onDismiss} className="ml-4 text-lg leading-none opacity-60 hover:opacity-100">✕</button>
    </div>
  );
}

function CopyBtn({ value }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
      className="ml-2 px-2 py-0.5 text-[10px] border rounded hover:bg-gray-100 text-gray-500 shrink-0">
      {copied ? '✓' : 'Copy'}
    </button>
  );
}

function DnsRow({ label, name, type, value }) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs space-y-1.5">
      <p className="font-semibold text-gray-500 uppercase tracking-wider text-[10px]">{label}</p>
      <div className="flex items-center gap-1">
        <span className="text-gray-400 w-10 shrink-0">Name</span>
        <code className="bg-white border rounded px-1.5 py-0.5 font-mono text-gray-800 flex-1 break-all">{name}</code>
        <CopyBtn value={name} />
      </div>
      <div className="flex items-center gap-1">
        <span className="text-gray-400 w-10 shrink-0">Type</span>
        <code className="bg-white border rounded px-1.5 py-0.5 font-mono text-gray-800">{type}</code>
      </div>
      <div className="flex items-start gap-1">
        <span className="text-gray-400 w-10 shrink-0 pt-0.5">Value</span>
        <code className="bg-white border rounded px-1.5 py-0.5 font-mono text-gray-800 flex-1 break-all">{value}</code>
        <CopyBtn value={value} />
      </div>
    </div>
  );
}

const STATUS_CLS = {
  pending:  'bg-yellow-100 text-yellow-800 border border-yellow-200',
  verified: 'bg-green-100  text-green-800  border border-green-200',
  failed:   'bg-red-100    text-red-800    border border-red-200',
};

// ─── Post-verify panel: A record + subdomain records from tracking config ──────
// trackingDomains = { open, click, unsub } — the effective domains currently saved.
// We extract subdomains that belong to THIS domain and show their A records.
function PostVerifyPanel({ domain, serverInfo, trackingDomains }) {
  const ip       = serverInfo?.public_ip;
  const ipLoading = !ip;
  const ipDisplay = ip || 'fetching…';

  // Extract subdomains that belong to this domain from the tracking config
  const subdomainsNeeded = [];
  const entries = [
    { key: 'open',  label: 'Open tracking',  value: trackingDomains.open  },
    { key: 'click', label: 'Click tracking',  value: trackingDomains.click },
    { key: 'unsub', label: 'Unsubscribe',     value: trackingDomains.unsub },
  ];
  for (const { label, value } of entries) {
    if (!value) continue;
    // Belongs to this domain if it IS the domain or ends with .domain
    if (value === domain.domain || value.endsWith(`.${domain.domain}`)) {
      subdomainsNeeded.push({ name: value, label });
    }
  }

  return (
    <div className="mt-4 space-y-3">
      <div className="bg-green-50 border border-green-200 px-4 py-3 rounded-lg text-xs text-green-800 flex items-start gap-2">
        <span className="text-base shrink-0">✓</span>
        <div>
          <p className="font-semibold">Ownership verified!</p>
          <p className="mt-0.5">Now add the DNS records below so tracking URLs resolve to this server.</p>
        </div>
      </div>

      {/* Server IP note */}
      <div className={`border rounded-lg px-3 py-2.5 text-[11px] flex items-start gap-2
        ${ipLoading ? 'bg-gray-50 border-gray-200 text-gray-500' : 'bg-blue-50 border-blue-100 text-blue-700'}`}>
        <span className="shrink-0">ℹ</span>
        <span>
          <strong>Server public IP:{' '}
            {ipLoading
              ? <span className="italic">detecting…</span>
              : <code className="font-mono">{ipDisplay}</code>
            }
          </strong>
          {!ipLoading && <> — Use this IP for all A records below. If behind a load balancer or reverse proxy, use its public IP instead. Set <code className="font-mono">SERVER_PUBLIC_IP</code> env var to override.</>}
        </span>
      </div>

      {/* Step 2 — Root domain A record */}
      <div>
        <p className="text-xs font-semibold text-gray-700 mb-1.5">
          Step 2 — Root domain A record
        </p>
        <DnsRow
          label={`A record — ${domain.domain}`}
          name={domain.domain}
          type="A"
          value={ipDisplay}
        />
      </div>

      {/* Step 3 — Subdomain A records (only from actual tracking config) */}
      <div>
        <p className="text-xs font-semibold text-gray-700 mb-1">
          Step 3 — Tracking subdomain A records
        </p>

        {subdomainsNeeded.length === 0 ? (
          <div className="text-xs text-gray-400 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2.5">
            No tracking subdomains configured yet. Set them in the <strong>Tracking Domains</strong> section
            below and come back here to see the records you need to add.
          </div>
        ) : (
          <div className="space-y-2">
            {subdomainsNeeded.map(({ name, label }) => (
              <DnsRow key={name} label={`${label} — ${name}`} name={name} type="A" value={ipDisplay} />
            ))}
          </div>
        )}

        <p className="text-[10px] text-gray-400 mt-2">
          Only subdomains you've configured in the Tracking Domains section appear here.
          All tracking paths (<code className="font-mono">/t/o/</code>, <code className="font-mono">/t/c/</code>,{' '}
          <code className="font-mono">/unsubscribe/</code>) are served by this application on the same IP.
        </p>
      </div>
    </div>
  );
}

// ─── Tracking toggle row ──────────────────────────────────────────────────────
function Toggle({ checked, onChange }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent
        transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2
        ${checked ? 'bg-indigo-600' : 'bg-gray-200'}`}>
      <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200
        ${checked ? 'translate-x-5' : 'translate-x-0'}`} />
    </button>
  );
}

function SettingRow({ icon, label, description, checked, onChange, badge }) {
  return (
    <div className="flex items-start justify-between gap-4 py-4">
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

// ─── Domain picker for tracking URL fields ────────────────────────────────────
// value = effective domain string saved (e.g. "track.example.com")
// onChange = fn(string)
function DomainPicker({ label, description, checkPath, value, onChange, verifiedDomains, loadingDomains }) {
  const [root,   setRoot]   = useState('');
  const [prefix, setPrefix] = useState('');
  const [checking,     setChecking]     = useState(false);
  const [checkResult,  setCheckResult]  = useState(null); // null | 'ok' | 'fail'

  // Parse saved value back into prefix + root on load
  useEffect(() => {
    if (!value) { setRoot(''); setPrefix(''); return; }
    const match = verifiedDomains.find(d => value === d.domain || value.endsWith(`.${d.domain}`));
    if (match) {
      setRoot(match.domain);
      setPrefix(value === match.domain ? '' : value.slice(0, value.length - match.domain.length - 1));
    } else {
      setRoot(value); setPrefix('');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, verifiedDomains.length]);

  const effective = prefix.trim() ? `${prefix.trim()}.${root}` : root;

  const handleRoot = (r) => {
    setRoot(r); setCheckResult(null);
    onChange(prefix.trim() ? `${prefix.trim()}.${r}` : r);
  };
  const handlePrefix = (p) => {
    const clean = p.toLowerCase().replace(/[^a-z0-9-]/g, '');
    setPrefix(clean); setCheckResult(null);
    onChange(clean ? `${clean}.${root}` : root);
  };

  const check = async () => {
    if (!effective) return;
    setChecking(true); setCheckResult(null);
    try {
      await fetch(`https://${effective}${checkPath}`, { method: 'GET', mode: 'no-cors', signal: AbortSignal.timeout(5000) });
      setCheckResult('ok');
    } catch { setCheckResult('fail'); }
    finally { setChecking(false); }
  };

  if (loadingDomains) return (
    <div className="py-4">
      <p className="text-sm font-semibold text-gray-800 mb-2">{label}</p>
      <div className="h-9 bg-gray-100 rounded-lg animate-pulse" />
    </div>
  );

  return (
    <div className="py-4">
      <label className="block text-sm font-semibold text-gray-800 mb-1">{label}</label>
      <p className="text-xs text-gray-500 mb-2 leading-relaxed">{description}</p>

      {verifiedDomains.length === 0 ? (
        <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5 text-xs text-amber-800">
          <span className="shrink-0">⚠</span>
          <span>No verified domains yet — add and verify a domain above first.</span>
        </div>
      ) : (
        <>
          <div className="flex items-stretch rounded-lg border border-gray-300 overflow-hidden focus-within:ring-2 focus-within:ring-indigo-400 bg-white">
            <input type="text" value={prefix} onChange={e => handlePrefix(e.target.value)}
              placeholder="subdomain" disabled={!root}
              className="w-28 px-3 py-2 text-sm font-mono outline-none border-none bg-transparent disabled:bg-gray-50 disabled:text-gray-400" />
            <span className="flex items-center px-1.5 text-gray-400 text-sm bg-gray-50 border-x border-gray-200 select-none">.</span>
            <select value={root} onChange={e => handleRoot(e.target.value)}
              className="flex-1 px-3 py-2 text-sm outline-none border-none bg-transparent cursor-pointer">
              <option value="">— select domain —</option>
              {verifiedDomains.map(d => <option key={d.id} value={d.domain}>{d.domain}</option>)}
            </select>
            <button type="button" onClick={check} disabled={!effective || checking}
              className="px-3 py-2 text-xs font-medium border-l border-gray-200 bg-gray-50 hover:bg-gray-100 disabled:opacity-40 whitespace-nowrap text-gray-600">
              {checking ? '…' : 'Check'}
            </button>
          </div>
          <div className="mt-1.5 flex items-center gap-3 flex-wrap">
            {effective && root
              ? <span className="text-xs text-gray-400">Effective: <code className="font-mono text-indigo-700 bg-indigo-50 px-1.5 py-0.5 rounded">{effective}</code></span>
              : <span className="text-xs text-gray-400 italic">No domain selected — server default will be used</span>
            }
            {checkResult === 'ok' && <span className="text-xs font-medium text-green-700 bg-green-50 border border-green-200 px-2 py-0.5 rounded-full">✓ Reachable</span>}
            {checkResult === 'fail' && <span className="text-xs font-medium text-red-700 bg-red-50 border border-red-200 px-2 py-0.5 rounded-full">✗ Not reachable — check DNS</span>}
          </div>
        </>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function DomainSettings() {
  const { t } = useSettings();
  // ── domain state
  const [domains,    setDomains]    = useState([]);
  const [newDomain,  setNewDomain]  = useState('');
  const [domainBusy, setDomainBusy] = useState(false);
  const [fetchErr,   setFetchErr]   = useState('');
  const [serverInfo, setServerInfo] = useState(null);
  const [openPanel,  setOpenPanel]  = useState(null); // { domainId, mode, records? }

  // ── tracking state
  const [tracking, setTracking] = useState({
    open_tracking_enabled:        true,
    click_tracking_enabled:       true,
    unsubscribe_tracking_enabled: true,
    track_unique_only:            true,
    open_tracking_domain:         '',
    click_tracking_domain:        '',
    unsubscribe_domain:           '',
  });
  const [trackingFetching, setTrackingFetching] = useState(true);
  const [trackingSaving,   setTrackingSaving]   = useState(false);
  const [trackingDirty,    setTrackingDirty]    = useState(false);
  const [verifiedDomains,  setVerifiedDomains]  = useState([]);
  const [loadingVerified,  setLoadingVerified]  = useState(true);

  // ── shared toast
  const [toast, setToast] = useState({ msg: '', type: 'success' });
  const notify    = (msg, type = 'success') => setToast({ msg, type });
  const clearToast = () => setToast({ msg: '', type: 'success' });

  // ── fetch domains
  const fetchDomains = useCallback(async () => {
    try {
      const res = await API.get('/domains');
      setDomains(Array.isArray(res.data) ? res.data : []);
      setFetchErr('');
    } catch { setFetchErr('Failed to load domains.'); }
  }, []);

  // ── fetch verified domains (for tracking pickers)
  const fetchVerified = useCallback(async () => {
    try {
      const res = await API.get('/domains/verified');
      setVerifiedDomains(res.data?.domains || []);
    } catch {}
    finally { setLoadingVerified(false); }
  }, []);

  useEffect(() => {
    fetchDomains();
    fetchVerified();
    API.get('/domains/server-info', { timeout: 8000 })
      .then(r => setServerInfo(r.data))
      .catch(() => setServerInfo({ public_ip: null }));
    API.get('/settings/tracking')
      .then(r => setTracking(t => ({ ...t, ...r.data })))
      .catch(() => notify('Failed to load tracking settings.', 'error'))
      .finally(() => setTrackingFetching(false));
  }, [fetchDomains, fetchVerified]);

  // ── domain actions
  const addDomain = async () => {
    const d = newDomain.trim().toLowerCase();
    if (!d) return;
    setDomainBusy(true);
    try {
      const res = await API.post('/domains', { domain: d });
      const added = res.data;
      setDomains(p => [added, ...p]);
      setNewDomain('');
      setOpenPanel({ domainId: added.id, mode: 'dns', records: added.verification_records });
      notify('Domain added — add the TXT record below, then click Verify.');
    } catch (e) { notify(e.response?.data?.detail || 'Failed to add domain.', 'error'); }
    finally { setDomainBusy(false); }
  };

  const verifyDomain = async (id) => {
    setDomainBusy(true);
    try {
      const res = await API.post(`/domains/${id}/verify`);
      setDomains(p => p.map(d => d.id === id ? { ...d, status: res.data.status } : d));
      if (res.data.status === 'verified') {
        setOpenPanel({ domainId: id, mode: 'post-verify' });
        await fetchVerified(); // refresh picker list
        notify('Domain verified ✓ — add the A records below to complete setup.');
      } else {
        notify('Verification failed — check your DNS and try again.', 'error');
      }
    } catch { notify('Verification request failed.', 'error'); }
    finally { setDomainBusy(false); }
  };

  const deleteDomain = async (id, name) => {
    if (!confirm(`Delete domain "${name}"?`)) return;
    try {
      await API.delete(`/domains/${id}`);
      setDomains(p => p.filter(d => d.id !== id));
      if (openPanel?.domainId === id) setOpenPanel(null);
      await fetchVerified();
      notify('Domain deleted.');
    } catch { notify('Failed to delete domain.', 'error'); }
  };

  const showDnsPanel = async (domain) => {
    if (openPanel?.domainId === domain.id && openPanel.mode === 'dns') { setOpenPanel(null); return; }
    try {
      const res = await API.get(`/domains/${domain.id}/verification-records`);
      setOpenPanel({ domainId: domain.id, mode: 'dns', records: res.data.verification_records });
    } catch { notify('Failed to load DNS records.', 'error'); }
  };

  // ── tracking actions
  const updateTracking = (key, val) => {
    setTracking(s => ({ ...s, [key]: val }));
    setTrackingDirty(true);
  };

  const saveTracking = async () => {
    setTrackingSaving(true);
    try {
      const payload = {
        open_tracking_enabled:        tracking.open_tracking_enabled,
        click_tracking_enabled:       tracking.click_tracking_enabled,
        unsubscribe_tracking_enabled: tracking.unsubscribe_tracking_enabled,
        track_unique_only:            tracking.track_unique_only,
        open_tracking_domain:         tracking.open_tracking_domain || '',
        click_tracking_domain:        tracking.click_tracking_domain || '',
        unsubscribe_domain:           tracking.unsubscribe_domain || '',
      };
      const res = await API.put('/settings/tracking', payload);
      if (res.data?.status === 'saved') {
        const { status, type, updated_at, ...srv } = res.data;
        setTracking(p => ({ ...p, ...srv }));
      }
      notify('Tracking settings saved.');
      setTrackingDirty(false);
    } catch (e) { notify(e.response?.data?.detail || 'Failed to save tracking settings.', 'error'); }
    finally { setTrackingSaving(false); }
  };

  const activeCount = [
    tracking.open_tracking_enabled,
    tracking.click_tracking_enabled,
    tracking.unsubscribe_tracking_enabled,
  ].filter(Boolean).length;

  // ─────────────────────────────────────────────────────────────────────────────

  return (
    <div className="max-w-3xl space-y-8">

      <Toast msg={toast.msg} type={toast.type} onDismiss={clearToast} />

      {/* ══════════════════════════════════════════════════════════════════════
          SECTION 1 — DOMAIN MANAGEMENT
      ══════════════════════════════════════════════════════════════════════ */}
      <div>
        <h2 className="text-lg font-bold text-gray-900">{t('domainSettings.title')}</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Add and verify your sending / tracking domains. After verification you'll see the DNS
          records needed to route tracking URLs to this server.
        </p>
      </div>

      {fetchErr && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm flex justify-between">
          {fetchErr} <button onClick={fetchDomains} className="underline ml-2">Retry</button>
        </div>
      )}

      {/* Add domain */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">{t('domainSettings.addDomain')}</h3>
        <div className="flex gap-3">
          <input type="text" placeholder="example.com" value={newDomain}
            onChange={e => setNewDomain(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addDomain()}
            className="flex-1 px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
          <button onClick={addDomain} disabled={domainBusy || !newDomain.trim()}
            className="px-5 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 whitespace-nowrap">
            {domainBusy ? 'Adding…' : `+ ${t('domainSettings.addDomain')}`}
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2">Root domain only (e.g. <code>example.com</code>). Tracking subdomains are configured in the Tracking Domains section below.</p>
      </div>

      {/* Domain list */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700">Your Domains</h3>
        </div>
        {domains.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-3xl mb-2">🌐</p>
            <p className="text-sm text-gray-500">No domains added yet</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-50">
            {domains.map(domain => (
              <div key={domain.id} className="px-5 py-4">
                {/* Row */}
                <div className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-gray-900 text-sm">{domain.domain}</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_CLS[domain.status] || STATUS_CLS.pending}`}>
                        {domain.status?.charAt(0).toUpperCase() + domain.status?.slice(1)}
                      </span>
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">Added {new Date(domain.created_at).toLocaleDateString()}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {(domain.status === 'pending' || domain.status === 'failed') && (<>
                      <button onClick={() => showDnsPanel(domain)}
                        className="px-2.5 py-1.5 text-xs font-medium border border-blue-200 rounded-lg hover:bg-blue-50 text-blue-700">
                        {t('domainSettings.dnsRecords')}
                      </button>
                      <button onClick={() => verifyDomain(domain.id)} disabled={domainBusy}
                        className="px-2.5 py-1.5 text-xs font-medium border border-green-200 rounded-lg hover:bg-green-50 text-green-700 disabled:opacity-50">
                        {domainBusy ? '…' : t('domainSettings.verify')}
                      </button>
                    </>)}
                    {domain.status === 'verified' && (
                      <button onClick={() => setOpenPanel(p => p?.domainId === domain.id && p.mode === 'post-verify' ? null : { domainId: domain.id, mode: 'post-verify' })}
                        className="px-2.5 py-1.5 text-xs font-medium border border-green-200 rounded-lg hover:bg-green-50 text-green-700">
                        Setup Records
                      </button>
                    )}
                    <button onClick={() => deleteDomain(domain.id, domain.domain)}
                      className="px-2.5 py-1.5 text-xs font-medium border border-red-200 rounded-lg hover:bg-red-50 text-red-600">
                      Delete
                    </button>
                  </div>
                </div>

                {/* TXT ownership panel */}
                {openPanel?.domainId === domain.id && openPanel.mode === 'dns' && openPanel.records && (
                  <div className="mt-4 space-y-3">
                    <div className="bg-amber-50 border border-amber-200 px-4 py-3 rounded-lg text-xs text-amber-800">
                      ⚠ Add this TXT record to your DNS provider to prove domain ownership.
                      DNS changes can take 5–30 minutes to propagate.
                    </div>
                    <DnsRow label="Ownership verification" name="_emailverify" type="TXT" value={openPanel.records.verification_token} />
                    <button onClick={() => verifyDomain(domain.id)} disabled={domainBusy}
                      className="w-full py-2 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 disabled:opacity-50">
                      {domainBusy ? 'Checking DNS…' : 'Verify Domain'}
                    </button>
                  </div>
                )}

                {/* Post-verify A + CNAME records */}
                {openPanel?.domainId === domain.id && openPanel.mode === 'post-verify' && (
                  <PostVerifyPanel
                    domain={domain}
                    serverInfo={serverInfo}
                    trackingDomains={{
                      open:  tracking.open_tracking_domain,
                      click: tracking.click_tracking_domain,
                      unsub: tracking.unsubscribe_domain,
                    }}
                  />
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ══════════════════════════════════════════════════════════════════════
          SECTION 2 — TRACKING SETTINGS
      ══════════════════════════════════════════════════════════════════════ */}
      <div className="border-t border-gray-200 pt-8">
        <h2 className="text-lg font-bold text-gray-900">Email Tracking</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Control what gets tracked when recipients interact with your emails.
          Changes apply to new sends only — not emails already in flight.
        </p>
      </div>

      {trackingFetching ? (
        <div className="space-y-3 animate-pulse">
          <div className="h-40 bg-gray-100 rounded-xl" />
          <div className="h-40 bg-gray-100 rounded-xl" />
        </div>
      ) : (<>

        {/* Active count bar */}
        <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-sm">
          <span className="text-gray-500 font-medium">Active tracking features:</span>
          <span className="font-bold text-gray-800">{activeCount} / 3</span>
          <span className="ml-auto">
            {activeCount === 3
              ? <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-green-100 text-green-700"><span className="w-1.5 h-1.5 rounded-full bg-green-500" />Active</span>
              : activeCount === 0
              ? <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-500"><span className="w-1.5 h-1.5 rounded-full bg-gray-400" />Disabled</span>
              : <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-700"><span className="w-1.5 h-1.5 rounded-full bg-amber-500" />Partial</span>
            }
          </span>
        </div>

        {/* Toggles */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm divide-y divide-gray-100">
          <div className="px-5"><SettingRow icon="👁️" label="Open Tracking"
            description="Inserts a 1×1 invisible pixel into every outgoing email. When a recipient opens the email their mail client loads the pixel, recording an open event."
            checked={tracking.open_tracking_enabled} onChange={v => updateTracking('open_tracking_enabled', v)} /></div>
          <div className="px-5"><SettingRow icon="🔗" label="Click Tracking"
            description="Rewrites links in your emails through a tracking redirect before delivery. Captures which links recipients click."
            checked={tracking.click_tracking_enabled} onChange={v => updateTracking('click_tracking_enabled', v)} /></div>
          <div className="px-5"><SettingRow icon="🚫" label="Unsubscribe Event Tracking" badge="Recommended on"
            description="Logs an event every time someone clicks an unsubscribe link. Disabling this does not stop unsubscribes — it only stops recording them in analytics."
            checked={tracking.unsubscribe_tracking_enabled} onChange={v => updateTracking('unsubscribe_tracking_enabled', v)} /></div>
          <div className="px-5"><SettingRow icon="1️⃣" label="Count Unique Events Only"
            description="Only the first open and first click per subscriber per campaign count toward analytics totals. Subsequent events are still logged."
            checked={tracking.track_unique_only} onChange={v => updateTracking('track_unique_only', v)} /></div>
        </div>

        {/* Tracking domains */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm px-5 divide-y divide-gray-100">
          <div className="py-4 -mb-1">
            <h3 className="text-sm font-bold text-gray-800">Tracking Domains</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Select a verified domain for each URL type. Optional subdomain prefix (e.g.{' '}
              <code className="font-mono text-xs">track</code> → <code className="font-mono text-xs">track.example.com</code>).
              Use <strong>Check</strong> to confirm the domain is reachable before saving.
            </p>
          </div>
          <DomainPicker
            label="Open Tracking Domain"
            description="Used for the 1×1 pixel URL. The path /t/o/<token>.gif must resolve to this server."
            checkPath="/t/o/healthcheck.gif"
            value={tracking.open_tracking_domain}
            onChange={v => updateTracking('open_tracking_domain', v)}
            verifiedDomains={verifiedDomains}
            loadingDomains={loadingVerified}
          />
          <DomainPicker
            label="Click Tracking Domain"
            description="Used for click-redirect links. The path /t/c/<token> must resolve to this server."
            checkPath="/t/c/healthcheck"
            value={tracking.click_tracking_domain}
            onChange={v => updateTracking('click_tracking_domain', v)}
            verifiedDomains={verifiedDomains}
            loadingDomains={loadingVerified}
          />
          <DomainPicker
            label="Unsubscribe Domain"
            description="Used for {{unsubscribe_url}} links. The path /unsubscribe/<token> must resolve to this server."
            checkPath="/unsubscribe/healthcheck"
            value={tracking.unsubscribe_domain}
            onChange={v => updateTracking('unsubscribe_domain', v)}
            verifiedDomains={verifiedDomains}
            loadingDomains={loadingVerified}
          />
        </div>

        {/* Save bar */}
        <div className="flex items-center justify-between">
          <p className="text-xs text-gray-400">{trackingDirty ? '● Unsaved changes' : 'All changes saved'}</p>
          <button onClick={saveTracking} disabled={trackingSaving || !trackingDirty}
            className="px-6 py-2.5 bg-indigo-600 text-white text-sm font-semibold rounded-xl
              hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
            {trackingSaving ? 'Saving…' : 'Save Tracking Settings'}
          </button>
        </div>

        {/* Privacy note */}
        <div className="flex gap-3 p-4 bg-blue-50 border border-blue-100 rounded-xl text-blue-800">
          <span className="text-lg flex-shrink-0">🔒</span>
          <div>
            <p className="text-sm font-semibold mb-1">Privacy consideration</p>
            <p className="text-xs text-blue-700 leading-relaxed">
              Disabling open tracking removes the pixel entirely. Disabling click tracking sends links
              without redirect wrapping. Both are appropriate for privacy-conscious audiences or
              regulations requiring minimal data collection.
            </p>
          </div>
        </div>

      </>)}
    </div>
  );
}