import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

const API = axios.create({ baseURL: import.meta.env.VITE_API_URL || '' });

/**
 * Public opt-in landing page.
 * Route: /subscribe/:listId
 *
 * - Fetches the list's actual field schema from the backend
 * - Renders standard + custom fields dynamically (same fields as the list uses)
 * - Sends data in the same standard_fields / custom_fields shape as SubscriberIn
 * - Double opt-in: success state shows "check your email"
 */
export default function OptInForm() {
  const { listId } = useParams();

  // page-level states: loading | idle | submitting | success | error | not_found
  const [pageState, setPageState] = useState('loading');

  const [listMeta, setListMeta] = useState(null);  // { list_name, standard_fields[], custom_fields[] }
  const [values, setValues] = useState({});         // { fieldKey: value }
  const [consent, setConsent] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [submittedEmail, setSubmittedEmail] = useState('');

  // ── 1. Load list field schema ──────────────────────────────────────────────
  useEffect(() => {
    if (!listId) { setPageState('not_found'); return; }

    API.get(`/api/public/list-meta/${encodeURIComponent(listId)}`)
      .then(res => {
        setListMeta(res.data);
        // Pre-initialize all field values to empty string
        // standard_fields is string[], custom_fields is { name, type }[]
        const initial = { email: '' };
        (res.data.standard_fields || []).forEach(f => { initial[f] = ''; });
        (res.data.custom_fields || []).forEach(f => { initial[f.name ?? f] = ''; });
        setValues(initial);
        setPageState('idle');
      })
      .catch(err => {
        if (err.response?.status === 404) setPageState('not_found');
        else setPageState('not_found'); // Any error → treat as not found (safe default)
      });
  }, [listId]);

  // ── 2. Submit ──────────────────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!consent) { setErrorMsg('You must give consent to subscribe.'); return; }

    setPageState('submitting');
    setErrorMsg('');

    // Split values back into standard_fields and custom_fields
    // standard_fields is string[], custom_fields is { name, type }[]
    const standardKeys = new Set(listMeta?.standard_fields || []);
    const customKeys = new Set((listMeta?.custom_fields || []).map(f => f.name ?? f));

    const standard_fields = {};
    const custom_fields = {};

    for (const [k, v] of Object.entries(values)) {
      if (k === 'email') continue;
      if (standardKeys.has(k)) standard_fields[k] = v;
      else if (customKeys.has(k)) custom_fields[k] = v;
    }

    try {
      await API.post('/api/public/opt-in', {
        email: values['email'].trim().toLowerCase(),
        consent: true,
        list_id: listId,
        source: 'public_form',
        standard_fields,
        custom_fields,
      });
      setSubmittedEmail(values['email']);
      setPageState('success');
    } catch (err) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;

      if (status === 404) { setPageState('not_found'); return; }
      if (status === 429) { setErrorMsg('Too many attempts. Please wait a moment.'); }
      else if (status === 422) {
        const d = err.response?.data?.detail;
        setErrorMsg(Array.isArray(d) ? d[0]?.msg : (d || 'Please check your input.'));
      } else {
        setErrorMsg(detail || 'Something went wrong. Please try again.');
      }
      setPageState('error');
    }
  };

  const handleChange = (key, val) =>
    setValues(prev => ({ ...prev, [key]: val }));

  // ── Render ─────────────────────────────────────────────────────────────────

  if (pageState === 'loading') return <Shell><Spinner /></Shell>;

  if (pageState === 'not_found') return (
    <Shell>
      <div className="text-center py-6">
        <div className="text-6xl mb-4">📭</div>
        <h2 className="text-xl font-semibold text-gray-800 mb-2">Form not found</h2>
        <p className="text-gray-500 text-sm">
          This subscription form is no longer active or the link is incorrect.
        </p>
      </div>
    </Shell>
  );

  if (pageState === 'success') return (
    <Shell>
      <div className="text-center py-6">
        <div className="text-6xl mb-4">📬</div>
        <h2 className="text-xl font-semibold text-gray-800 mb-2">Check your inbox!</h2>
        <p className="text-gray-600 text-sm mb-1">
          We sent a confirmation email to:
        </p>
        <p className="font-medium text-gray-900 mb-4">{submittedEmail}</p>
        <p className="text-gray-400 text-xs">
          Click the link in that email to complete your subscription.
          Check your spam folder if you don't see it.
        </p>
      </div>
    </Shell>
  );

  const isSubmitting = pageState === 'submitting';
  const standardFields = listMeta?.standard_fields || [];
  const customFields = listMeta?.custom_fields || [];

  return (
    <Shell>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Subscribe</h1>
        <p className="text-sm text-gray-500 mt-1">
          Join the <span className="font-medium text-gray-700">{listId}</span> mailing list.
        </p>
      </div>

      {/* Error banner */}
      {pageState === 'error' && errorMsg && (
        <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
          {errorMsg}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">

        {/* Email — always first */}
        <Field label="Email address" required>
          <input
            type="email"
            required
            autoComplete="email"
            placeholder="you@example.com"
            value={values['email'] || ''}
            onChange={e => handleChange('email', e.target.value)}
            disabled={isSubmitting}
            className={inputCls}
          />
        </Field>

        {/* Standard fields — rendered in order returned by API */}
        {standardFields.map(key => (
          <Field key={key} label={labelFor(key)}>
            <input
              type={inputTypeFor(key)}
              autoComplete={autoCompleteFor(key)}
              placeholder={placeholderFor(key)}
              value={values[key] || ''}
              onChange={e => handleChange(key, e.target.value)}
              disabled={isSubmitting}
              className={inputCls}
            />
          </Field>
        ))}

        {/* Custom fields — API returns { name, type } objects */}
        {customFields.map(field => {
          const key = field.name ?? field;
          return (
            <Field key={key} label={labelFor(key)}>
              <input
                type="text"
                placeholder={placeholderFor(key)}
                value={values[key] || ''}
                onChange={e => handleChange(key, e.target.value)}
                disabled={isSubmitting}
                className={inputCls}
              />
            </Field>
          );
        })}

        {/* GDPR consent */}
        <div className="flex items-start gap-3 pt-1">
          <input
            id="consent"
            type="checkbox"
            checked={consent}
            onChange={e => setConsent(e.target.checked)}
            disabled={isSubmitting}
            required
            className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600
                       focus:ring-blue-500 cursor-pointer flex-shrink-0"
          />
          <label htmlFor="consent" className="text-sm text-gray-600 cursor-pointer leading-5">
            I agree to receive marketing emails and confirm I have read the privacy policy.
            I can unsubscribe at any time.{' '}
            <span className="text-red-500">*</span>
          </label>
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700
                     text-white text-sm font-semibold rounded-lg shadow-sm
                     transition-colors focus:outline-none focus:ring-2
                     focus:ring-offset-2 focus:ring-blue-500
                     disabled:opacity-60 disabled:cursor-not-allowed mt-2"
        >
          {isSubmitting ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor"
                  strokeWidth="4" className="opacity-25" />
                <path fill="currentColor" className="opacity-75"
                  d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Subscribing…
            </span>
          ) : 'Subscribe'}
        </button>
      </form>
    </Shell>
  );
}

// ── Layout wrapper ─────────────────────────────────────────────────────────────
function Shell({ children }) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50
                    flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
          {children}
        </div>
        <p className="text-center text-xs text-gray-400 mt-4">
          Powered by ZeniPost · Your data is safe
        </p>
      </div>
    </div>
  );
}

// ── Field wrapper ──────────────────────────────────────────────────────────────
function Field({ label, required, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}

function Spinner() {
  return (
    <div className="flex justify-center py-8">
      <svg className="animate-spin h-8 w-8 text-blue-500" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="currentColor"
          strokeWidth="4" className="opacity-25" />
        <path fill="currentColor" className="opacity-75" d="M4 12a8 8 0 018-8v8H4z" />
      </svg>
    </div>
  );
}

// ── Shared input class ─────────────────────────────────────────────────────────
const inputCls = `w-full px-3 py-2 border border-gray-200 rounded-lg text-sm
  bg-white text-gray-900 placeholder-gray-400
  focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
  disabled:bg-gray-50 disabled:text-gray-400 transition-shadow`;

// ── Field metadata helpers ─────────────────────────────────────────────────────
// Maps field key → human-readable label, input type, autocomplete, placeholder.
// Falls back gracefully for unknown custom field names.

const FIELD_META = {
  first_name: { label: 'First name', type: 'text', ac: 'given-name', ph: 'Jane' },
  last_name: { label: 'Last name', type: 'text', ac: 'family-name', ph: 'Doe' },
  phone: { label: 'Phone number', type: 'tel', ac: 'tel', ph: '+1 555 000 0000' },
  company: { label: 'Company', type: 'text', ac: 'organization', ph: 'Acme Inc.' },
  job_title: { label: 'Job title', type: 'text', ac: 'organization-title', ph: 'Marketing Manager' },
  country: { label: 'Country', type: 'text', ac: 'country-name', ph: 'United States' },
  city: { label: 'City', type: 'text', ac: 'address-level2', ph: 'New York' },
  state: { label: 'State', type: 'text', ac: 'address-level1', ph: 'NY' },
  zip_code: { label: 'ZIP / Postcode', type: 'text', ac: 'postal-code', ph: '10001' },
  website: { label: 'Website', type: 'url', ac: 'url', ph: 'https://example.com' },
  date_of_birth: { label: 'Date of birth', type: 'date', ac: 'bday', ph: '' },
  language: { label: 'Language', type: 'text', ac: 'language', ph: 'English' },
  timezone: { label: 'Timezone', type: 'text', ac: 'off', ph: 'America/New_York' },
  gender: { label: 'Gender', type: 'text', ac: 'sex', ph: '' },
};

function labelFor(key) {
  return FIELD_META[key]?.label ?? key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
function inputTypeFor(key) { return FIELD_META[key]?.type ?? 'text'; }
function autoCompleteFor(key) { return FIELD_META[key]?.ac ?? 'off'; }
function placeholderFor(key) { return FIELD_META[key]?.ph ?? ''; }