import { useState, useEffect, useCallback } from 'react';
import API from '../api';

// ─── helpers ────────────────────────────────────────────────
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
  return (
    <div className={`flex items-center gap-2 px-4 py-3 rounded-lg text-sm font-medium ${msg.type === 'success' ? 'bg-green-50 border border-green-200 text-green-800' : msg.type === 'error' ? 'bg-red-50 border border-red-200 text-red-800' : 'bg-blue-50 border border-blue-200 text-blue-800'}`}>
      {msg.type === 'success' ? '✓' : msg.type === 'error' ? '✕' : 'ℹ'} {msg.text}
    </div>
  );
}

function CopyButton({ value }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* ignore */ }
  };
  return (
    <button onClick={copy} title="Copy to clipboard"
      className="flex-shrink-0 px-2 py-1 text-xs border border-gray-200 rounded hover:bg-gray-100 text-gray-500 transition-colors">
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  );
}

function DnsRecord({ title, records }) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 space-y-3">
      <h4 className="text-sm font-semibold text-gray-700">{title}</h4>
      {records.map(({ label, value }) => (
        <div key={label}>
          <p className="text-xs font-medium text-gray-500 mb-1">{label}</p>
          <div className="flex items-start gap-2">
            <code className="flex-1 bg-white border border-gray-200 px-3 py-1.5 rounded-lg text-xs break-all text-gray-800 font-mono leading-relaxed">
              {value}
            </code>
            <CopyButton value={value} />
          </div>
        </div>
      ))}
    </div>
  );
}

const STATUS_STYLE = {
  pending:  'bg-yellow-100 text-yellow-800',
  verified: 'bg-green-100  text-green-800',
  failed:   'bg-red-100    text-red-800',
};

export default function DomainSettings() {
  const [domains,             setDomains]             = useState([]);
  const [newDomain,           setNewDomain]           = useState('');
  const [loading,             setLoading]             = useState(false);
  const [fetchError,          setFetchError]          = useState(null);
  const [verificationDetails, setVerificationDetails] = useState(null);
  const [selectedDomain,      setSelectedDomain]      = useState(null);
  const { msg, show: toast }                          = useToast();

  useEffect(() => { fetchDomains(); }, []);

  const fetchDomains = async () => {
    setFetchError(null);
    try {
      const res = await API.get('/domains');
      setDomains(Array.isArray(res.data) ? res.data : []);
    } catch {
      setFetchError('Failed to load domains. Please refresh.');
      setDomains([]);
    }
  };

  const addDomain = async () => {
    if (!newDomain.trim()) return;
    setLoading(true);
    try {
      const res = await API.post('/domains', { domain: newDomain.trim().toLowerCase() });
      setDomains(p => [...p, res.data]);
      setNewDomain('');
      setVerificationDetails(res.data.verification_records);
      setSelectedDomain(res.data);
      toast('Domain added! Add the DNS records below to verify.', 'success');
    } catch (err) {
      toast(err.response?.data?.detail || 'Failed to add domain.', 'error');
    } finally { setLoading(false); }
  };

  const verifyDomain = async (domainId) => {
    setLoading(true);
    try {
      const res = await API.post(`/domains/${domainId}/verify`);
      setDomains(p => p.map(d => d.id === domainId ? { ...d, status: res.data.status } : d));
      if (res.data.status === 'verified') {
        toast('Domain verified successfully! ✓', 'success');
      } else {
        toast('Verification failed — check your DNS records and try again.', 'error');
      }
    } catch {
      toast('Verification failed. Please try again.', 'error');
    } finally { setLoading(false); }
  };

  const deleteDomain = async (domainId, domainName) => {
    if (!confirm(`Delete domain "${domainName}"?`)) return;
    try {
      await API.delete(`/domains/${domainId}`);
      setDomains(p => p.filter(d => d.id !== domainId));
      if (selectedDomain?.id === domainId) { setVerificationDetails(null); setSelectedDomain(null); }
      toast('Domain deleted', 'success');
    } catch {
      toast('Failed to delete domain.', 'error');
    }
  };

  const showVerificationDetails = async (domain) => {
    try {
      const res = await API.get(`/domains/${domain.id}/verification-records`);
      setVerificationDetails(res.data.verification_records);
      setSelectedDomain(domain);
    } catch { toast('Failed to load DNS records.', 'error'); }
  };

  return (
    <div className="max-w-3xl space-y-6">

      <InlineMsg msg={msg} />

      {fetchError && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm flex items-center justify-between">
          {fetchError}
          <button onClick={fetchDomains} className="underline ml-2">Retry</button>
        </div>
      )}

      {/* ── Domain List ── */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700">Your Domains</h2>
        </div>

        {domains.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-3xl mb-2">🌐</p>
            <p className="text-sm text-gray-500">No domains added yet</p>
            <p className="text-xs text-gray-400 mt-1">Add a domain below to set up custom sending</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Domain</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-24">Status</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-24">Added</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-48">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {domains.map(domain => (
                <tr key={domain.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-5 py-3.5 font-medium text-gray-900">{domain.domain}</td>
                  <td className="px-4 py-3.5">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[domain.status] || STATUS_STYLE.pending}`}>
                      {domain.status?.charAt(0).toUpperCase() + domain.status?.slice(1)}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-xs text-gray-400 text-right whitespace-nowrap">
                    {new Date(domain.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex items-center justify-end gap-2">
                      {domain.status === 'pending' && (
                        <button onClick={() => showVerificationDetails(domain)}
                          className="px-2.5 py-1.5 text-xs font-medium border border-blue-200 rounded-lg hover:bg-blue-50 text-blue-700">
                          DNS Records
                        </button>
                      )}
                      {(domain.status === 'pending' || domain.status === 'failed') && (
                        <button onClick={() => verifyDomain(domain.id)} disabled={loading}
                          className="px-2.5 py-1.5 text-xs font-medium border border-green-200 rounded-lg hover:bg-green-50 text-green-700 disabled:opacity-50">
                          {loading ? '⏳' : domain.status === 'failed' ? 'Retry' : 'Verify'}
                        </button>
                      )}
                      {domain.status === 'verified' && (
                        <button onClick={() => showVerificationDetails(domain)}
                          className="px-2.5 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600">
                          Records
                        </button>
                      )}
                      <button onClick={() => deleteDomain(domain.id, domain.domain)}
                        className="px-2.5 py-1.5 text-xs font-medium border border-red-200 rounded-lg hover:bg-red-50 text-red-600">
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Add domain ── */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Add New Domain</h2>
        <div className="flex gap-3">
          <input type="text" placeholder="example.com" value={newDomain}
            onChange={e => setNewDomain(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addDomain()}
            className="flex-1 px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
          <button onClick={addDomain} disabled={loading || !newDomain.trim()}
            className="px-5 py-2.5 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap">
            {loading ? '⏳ Adding…' : '+ Add Domain'}
          </button>
        </div>
      </div>

      {/* ── DNS Records panel ── */}
      {verificationDetails && selectedDomain && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <div>
              <h3 className="text-sm font-semibold text-gray-700">DNS Records — {selectedDomain.domain}</h3>
              <p className="text-xs text-gray-400 mt-0.5">Add all records to your DNS provider, then click Verify</p>
            </div>
            <button onClick={() => { setVerificationDetails(null); setSelectedDomain(null); }}
              className="text-gray-400 hover:text-gray-600 text-xl">✕</button>
          </div>

          <div className="p-5 space-y-4">
            <div className="bg-amber-50 border border-amber-200 px-4 py-3 rounded-lg text-xs text-amber-800">
              ⚠️ DNS changes can take 5–30 minutes to propagate. Click Verify after adding all records.
            </div>

            <DnsRecord title="📧 SPF Record (TXT)" records={[
              { label: 'Name', value: '@' },
              { label: 'Type', value: 'TXT' },
              { label: 'Value', value: verificationDetails.spf_record },
            ]} />

            <DnsRecord title="🔐 DKIM Record (TXT)" records={[
              { label: 'Name', value: `${verificationDetails.dkim_selector}._domainkey` },
              { label: 'Type', value: 'TXT' },
              { label: 'Value', value: verificationDetails.dkim_record },
            ]} />

            <DnsRecord title="🛡️ DMARC Record (TXT)" records={[
              { label: 'Name', value: '_dmarc' },
              { label: 'Type', value: 'TXT' },
              { label: 'Value', value: verificationDetails.dmarc_record },
            ]} />

            <DnsRecord title="✅ Domain Verification (TXT)" records={[
              { label: 'Name', value: '_emailverify' },
              { label: 'Type', value: 'TXT' },
              { label: 'Value', value: verificationDetails.verification_token },
            ]} />

            <div className="flex justify-end pt-2">
              <button onClick={() => verifyDomain(selectedDomain.id)} disabled={loading}
                className="px-5 py-2.5 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 disabled:opacity-50">
                {loading ? '⏳ Verifying…' : '✓ Verify Domain Now'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}