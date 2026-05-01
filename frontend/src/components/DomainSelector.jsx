// frontend/src/components/DomainSelector.jsx
//
// Reusable component for picking the sending domain in Campaign, AB Test,
// and Automation email step forms.
//
// Props
// ─────
// localPart   string   — the part before @  (e.g. "hello")
// domain      string   — current @domain value
// onChange    fn(localPart, domain) — called on any change
// label       string?  — field label  (default "From Email")
// required    bool?
// error       string?  — validation error message
//
// Behaviour
// ─────────
// • Fetches GET /domains/verified on mount.
// • If 0 verified domains: shows a plain free-text input + warning banner.
// • If 1 verified domain:  auto-selects it, shows it as read-only badge.
// • If 2+ verified domains: shows a dropdown of domains next to the local-part input.
//
// The component always keeps localPart and domain split so parent forms can
// assemble `sender_email` as `${localPart}@${domain}` and also control them
// independently (e.g. editing only localPart while domain is locked).

import { useState, useEffect } from 'react';
import API from '../api';

export default function DomainSelector({
  localPart = '',
  domain = '',
  onChange,
  label = 'From Email',
  required = false,
  error = '',
}) {
  const [verifiedDomains, setVerifiedDomains] = useState([]); // [{ domain, effective_domain }]
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    API.get('/domains/verified')
      .then(res => {
        const domains = res.data?.domains || [];
        setVerifiedDomains(domains);

        // Auto-select single verified domain if parent hasn't set one yet
        if (!domain && domains.length === 1) {
          onChange(localPart, domains[0].domain);
        }
      })
      .catch(() => {
        // Silently degrade — plain text input remains functional
      })
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const inputBase = 'px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none';
  const errCls    = error ? 'border-red-400 bg-red-50' : 'border-gray-300';

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>

      {/* No verified domains warning */}
      {!loading && verifiedDomains.length === 0 && (
        <div className="mb-2 flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-800">
          <span className="text-base shrink-0">⚠</span>
          <span>
            No verified domains found.{' '}
            <a href="/settings/domain" className="underline font-medium">
              Add and verify a domain
            </a>{' '}
            to use it as your sending domain.
          </span>
        </div>
      )}

      <div className={`flex items-stretch rounded-lg border overflow-hidden ${error ? 'border-red-400' : 'border-gray-300'} focus-within:ring-2 focus-within:ring-blue-500`}>
        {/* Local part input */}
        <input
          type="text"
          value={localPart}
          onChange={e => onChange(e.target.value.replace(/\s/g, ''), domain)}
          placeholder="hello"
          className={`flex-1 px-3 py-2 text-sm outline-none border-none ${error ? 'bg-red-50' : 'bg-white'}`}
        />

        {/* @ separator */}
        <span className="flex items-center px-2 text-sm text-gray-400 bg-gray-50 border-x border-gray-300 select-none">@</span>

        {/* Domain — dropdown if multiple, badge if single, free text if none */}
        {loading ? (
          <div className="flex items-center px-3 bg-gray-50 text-sm text-gray-400 min-w-32">
            Loading…
          </div>
        ) : verifiedDomains.length > 1 ? (
          <select
            value={domain}
            onChange={e => onChange(localPart, e.target.value)}
            className={`px-3 py-2 text-sm outline-none border-none bg-white cursor-pointer ${error ? 'bg-red-50' : ''}`}
          >
            <option value="">— select domain —</option>
            {verifiedDomains.map(d => (
              <option key={d.id} value={d.domain}>{d.domain}</option>
            ))}
          </select>
        ) : verifiedDomains.length === 1 ? (
          <div className="flex items-center px-3 bg-gray-50 text-sm text-gray-700 font-mono select-none">
            {verifiedDomains[0].domain}
          </div>
        ) : (
          // No verified domains — allow free text so form remains usable
          <input
            type="text"
            value={domain}
            onChange={e => onChange(localPart, e.target.value.trim().toLowerCase())}
            placeholder="yourdomain.com"
            className={`px-3 py-2 text-sm outline-none border-none font-mono ${error ? 'bg-red-50' : 'bg-white'}`}
          />
        )}
      </div>

      {/* Effective sender address preview */}
      {(localPart || domain) && (
        <p className="text-xs text-gray-400 mt-1">
          Will send as:{' '}
          <span className="font-mono text-gray-600">
            {localPart || '…'}@{domain || '…'}
          </span>
        </p>
      )}

      {error && <p className="text-xs text-red-600 mt-1">{error}</p>}
    </div>
  );
}