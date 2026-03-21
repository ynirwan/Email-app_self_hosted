import { useState, useEffect } from 'react';
import API from '../api';

export default function EmailSettings() {
  const [systemInfo, setSystemInfo] = useState(null);
  const [settings, setSettings]     = useState({
    smtp_choice: 'managed', provider: '', smtp_server: '', smtp_port: 587,
    username: '', password: '', ses_type: null, aws_region: 'us-east-1',
    ses_configuration_set: '', bounce_forward_email: ''
  });
  const [usage,   setUsage]   = useState(null);
  const [saving,  setSaving]  = useState(false);
  const [testing, setTesting] = useState(false);
  const [loading, setLoading] = useState(true);

  // Inline feedback instead of alert()
  const [saveMsg,  setSaveMsg]  = useState(null);   // { type: 'success'|'error', text }
  const [testMsg,  setTestMsg]  = useState(null);
  const [loadErr,  setLoadErr]  = useState(null);

  const isHostedService = systemInfo?.deployment_mode === 'hosted_service';

  const providerConfigs = {
    sendgrid: { name: 'SendGrid', smtp_server: 'smtp.sendgrid.net', smtp_port: 587, usernameLabel: 'API Key', passwordLabel: 'Password', helpText: 'Use your SendGrid API key as the username' },
    mailgun:  { name: 'Mailgun',  smtp_server: 'smtp.mailgun.org',  smtp_port: 587, usernameLabel: 'Username', passwordLabel: 'Password', helpText: 'Get SMTP credentials from Mailgun dashboard' },
    postmark: { name: 'Postmark', smtp_server: 'smtp.postmarkapp.com', smtp_port: 587, usernameLabel: 'Server API Token', passwordLabel: 'Server API Token', helpText: 'Use the same Server API Token for both fields' },
    custom:   { name: 'Custom SMTP', smtp_server: '', smtp_port: 587, usernameLabel: 'Username', passwordLabel: 'Password', helpText: 'Configure your custom SMTP server' },
  };

  const awsRegions = [
    { value: 'us-east-1',      label: 'US East (N. Virginia)' },
    { value: 'us-west-2',      label: 'US West (Oregon)' },
    { value: 'eu-west-1',      label: 'Europe (Ireland)' },
    { value: 'eu-central-1',   label: 'Europe (Frankfurt)' },
    { value: 'ap-south-1',     label: 'Asia Pacific (Mumbai)' },
    { value: 'ap-southeast-1', label: 'Asia Pacific (Singapore)' },
    { value: 'ap-southeast-2', label: 'Asia Pacific (Sydney)' },
    { value: 'ap-northeast-1', label: 'Asia Pacific (Tokyo)' },
  ];

  useEffect(() => { fetchData(); }, []);

  const fetchData = async () => {
    setLoadErr(null);
    try {
      setLoading(true);
      const [sysRes, settingsRes] = await Promise.all([
        API.get('/email/system-info'),
        API.get('/email/settings'),
      ]);
      setSystemInfo(sysRes.data);
      setSettings(settingsRes.data);
      if (sysRes.data.deployment_mode === 'hosted_service') {
        try { const r = await API.get('/email/usage'); setUsage(r.data); } catch { /* optional */ }
      }
    } catch {
      setLoadErr('Failed to load email settings. Please refresh.');
    } finally { setLoading(false); }
  };

  const handleProviderChange = (provider) => {
    const config = providerConfigs[provider];
    if (provider === 'amazonses') {
      setSettings(p => ({ ...p, provider: 'amazonses', ses_type: null, smtp_server: '', smtp_port: 587, aws_region: 'us-east-1' }));
    } else if (config) {
      setSettings(p => ({ ...p, provider, smtp_server: config.smtp_server, smtp_port: config.smtp_port, ses_type: null }));
    }
  };

  const handleSESTypeChange = (sesType) => {
    if (sesType === 'api') {
      setSettings(p => ({ ...p, ses_type: 'api', smtp_server: '', smtp_port: 587 }));
    } else if (sesType === 'smtp') {
      setSettings(p => ({ ...p, ses_type: 'smtp', smtp_server: `email-smtp.${p.aws_region}.amazonaws.com`, smtp_port: 587 }));
    }
  };

  const handleAWSRegionChange = (region) => {
    setSettings(p => ({
      ...p, aws_region: region,
      smtp_server: p.ses_type === 'smtp' ? `email-smtp.${region}.amazonaws.com` : p.smtp_server,
    }));
  };

  const saveSettings = async () => {
    setSaving(true); setSaveMsg(null);
    try {
      await API.put('/email/settings', settings);
      setSaveMsg({ type: 'success', text: 'Email settings saved successfully!' });
      fetchData();
    } catch (err) {
      setSaveMsg({ type: 'error', text: err.response?.data?.detail || 'Failed to save settings' });
    } finally { setSaving(false); }
  };

  const testConnection = async () => {
    setTesting(true); setTestMsg(null);
    try {
      const res = await API.post('/email/test-connection', {
        provider: settings.provider, smtp_server: settings.smtp_server,
        smtp_port: settings.smtp_port, username: settings.username,
        password: settings.password, ses_type: settings.ses_type, aws_region: settings.aws_region,
      });
      setTestMsg({ type: 'success', text: res.data.message || 'Connection successful!' });
    } catch (err) {
      setTestMsg({ type: 'error', text: err.response?.data?.detail || 'Connection test failed' });
    } finally { setTesting(false); }
  };

  if (loading) return (
    <div className="flex items-center justify-center h-64 gap-3 text-gray-400">
      <div className="animate-spin h-5 w-5 border-2 border-gray-300 border-t-blue-500 rounded-full" />
      Loading email settings…
    </div>
  );

  if (loadErr) return (
    <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm flex items-center gap-3">
      ⚠️ {loadErr}
      <button onClick={fetchData} className="underline ml-1">Retry</button>
    </div>
  );

  const currentProviderConfig = providerConfigs[settings.provider] || providerConfigs.custom;

  const InlineMsg = ({ msg }) => msg ? (
    <div className={`flex items-center gap-2 px-4 py-3 rounded-lg text-sm font-medium ${msg.type === 'success' ? 'bg-green-50 border border-green-200 text-green-800' : 'bg-red-50 border border-red-200 text-red-800'}`}>
      {msg.type === 'success' ? '✓' : '✕'} {msg.text}
    </div>
  ) : null;

  return (
    <div className="max-w-4xl space-y-6">

      {/* Deployment info banner */}
      <div className="bg-blue-50 border border-blue-200 px-4 py-3 rounded-lg text-sm text-blue-800">
        <strong>Deployment Mode:</strong> {isHostedService ? '☁️ Hosted Service' : '🏠 Self-Hosted'} ·{' '}
        {isHostedService ? 'Managed infrastructure with quota enforced per your subscription plan.' : 'Full control over email sending — connect any provider.'}
      </div>

      {/* SMTP choice (hosted only) */}
      {isHostedService && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">SMTP Configuration Type</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              { value: 'managed', label: '🚀 Managed SMTP', desc: 'Premium email service managed by us', points: ['High deliverability', 'Managed infrastructure', 'Quota based on plan'], color: 'green' },
              { value: 'client',  label: '⚙️ Your SMTP',    desc: 'Use your own SMTP provider',           points: ['Use your own provider', 'Full control', 'No additional cost'], color: 'blue' },
            ].map(opt => (
              <div key={opt.value} onClick={() => setSettings(p => ({ ...p, smtp_choice: opt.value }))}
                className={`p-5 border-2 rounded-xl cursor-pointer transition-all ${settings.smtp_choice === opt.value ? `border-${opt.color}-500 bg-${opt.color}-50` : 'border-gray-200 hover:border-gray-300'}`}>
                <div className="flex items-center gap-2 mb-2">
                  <input type="radio" checked={settings.smtp_choice === opt.value} readOnly className="flex-shrink-0" />
                  <h3 className="text-sm font-semibold">{opt.label}</h3>
                </div>
                <p className="text-xs text-gray-500 mb-3">{opt.desc}</p>
                <ul className="space-y-1">
                  {opt.points.map(p => (
                    <li key={p} className="flex items-center gap-1.5 text-xs text-gray-600">
                      <span className={`text-${opt.color}-500`}>✓</span> {p}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Provider config (client SMTP) */}
      {(isHostedService ? settings.smtp_choice === 'client' : true) && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm space-y-5">
          <h2 className="text-sm font-semibold text-gray-700">Email Provider</h2>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">Select Provider</label>
            <select className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
              value={settings.provider || ''}
              onChange={e => handleProviderChange(e.target.value)}>
              <option value="">Choose provider…</option>
              <option value="amazonses">🟠 Amazon SES (API or SMTP)</option>
              <option value="sendgrid">SendGrid</option>
              <option value="mailgun">Mailgun</option>
              <option value="postmark">Postmark</option>
              <option value="custom">Custom SMTP</option>
            </select>
          </div>

          {/* SES config */}
          {settings.provider === 'amazonses' && (
            <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 space-y-4">
              <h3 className="text-sm font-semibold text-orange-900">Amazon SES Configuration</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {[
                  { type: 'api',  title: 'SES API (boto3)', desc: 'IAM Access Key + Secret Key', points: ['More features', 'Better error handling', 'Requires boto3'] },
                  { type: 'smtp', title: 'SES SMTP',         desc: 'SMTP username + password',   points: ['Standard SMTP', 'From IAM credentials', 'Easier setup'] },
                ].map(opt => (
                  <div key={opt.type} onClick={() => handleSESTypeChange(opt.type)}
                    className={`p-4 border-2 rounded-xl cursor-pointer transition-all ${settings.ses_type === opt.type ? 'border-orange-500 bg-white' : 'border-gray-200 bg-white hover:border-orange-300'}`}>
                    <div className="flex items-center gap-2 mb-1">
                      <input type="radio" checked={settings.ses_type === opt.type} readOnly />
                      <h4 className="text-sm font-semibold">{opt.title}</h4>
                    </div>
                    <p className="text-xs text-gray-500 mb-2">{opt.desc}</p>
                    <ul className="space-y-0.5">
                      {opt.points.map(p => <li key={p} className="text-xs text-gray-500">· {p}</li>)}
                    </ul>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">AWS Region</label>
                  <select className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-orange-500"
                    value={settings.aws_region} onChange={e => handleAWSRegionChange(e.target.value)}>
                    {awsRegions.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Configuration Set <span className="text-gray-400 font-normal">(optional)</span></label>
                  <input type="text" placeholder="my-configuration-set"
                    className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-orange-500"
                    value={settings.ses_configuration_set || ''}
                    onChange={e => setSettings(p => ({ ...p, ses_configuration_set: e.target.value }))} />
                </div>
              </div>
            </div>
          )}

          {/* Credentials */}
          {settings.provider && settings.provider !== 'amazonses' && (
            <div className="space-y-4">
              <div>
                <p className="text-sm font-medium text-gray-700 mb-0.5">{currentProviderConfig.name} Credentials</p>
                <p className="text-xs text-gray-400">{currentProviderConfig.helpText}</p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Field label="SMTP Server *" value={settings.smtp_server || ''} onChange={v => setSettings(p => ({ ...p, smtp_server: v }))} placeholder="smtp.provider.com" />
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Port *</label>
                  <select className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                    value={settings.smtp_port || 587} onChange={e => setSettings(p => ({ ...p, smtp_port: parseInt(e.target.value) }))}>
                    <option value={587}>587 (STARTTLS)</option>
                    <option value={465}>465 (SSL)</option>
                    <option value={25}>25 (Plain)</option>
                    <option value={2525}>2525 (Alternative)</option>
                  </select>
                </div>
                <Field label={`${currentProviderConfig.usernameLabel} *`} value={settings.username || ''} onChange={v => setSettings(p => ({ ...p, username: v }))} placeholder={currentProviderConfig.usernameLabel} />
                <Field label={`${currentProviderConfig.passwordLabel} *`} type="password" value={settings.password || ''} onChange={v => setSettings(p => ({ ...p, password: v }))} placeholder={currentProviderConfig.passwordLabel} />
              </div>
            </div>
          )}

          {settings.provider === 'amazonses' && settings.ses_type && (
            <div className="space-y-4">
              <p className="text-sm font-medium text-gray-700">
                Amazon SES {settings.ses_type === 'api' ? 'API' : 'SMTP'} Credentials
              </p>
              {settings.ses_type === 'api' ? (
                <div className="space-y-3">
                  <Field label="AWS Access Key ID *" value={settings.username || ''} onChange={v => setSettings(p => ({ ...p, username: v }))} placeholder="AKIAIOSFODNN7EXAMPLE" />
                  <Field label="AWS Secret Access Key *" type="password" value={settings.password || ''} onChange={v => setSettings(p => ({ ...p, password: v }))} placeholder="wJalrXUtn…" />
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1.5">SMTP Server (auto-filled)</label>
                    <input type="text" readOnly value={settings.smtp_server}
                      className="w-full px-3 py-2.5 border rounded-lg text-sm bg-gray-50 text-gray-500" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1.5">Port</label>
                    <select className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-orange-500"
                      value={settings.smtp_port || 587} onChange={e => setSettings(p => ({ ...p, smtp_port: parseInt(e.target.value) }))}>
                      <option value={587}>587 (STARTTLS)</option>
                      <option value={465}>465 (SSL)</option>
                    </select>
                  </div>
                  <Field label="SMTP Username *" value={settings.username || ''} onChange={v => setSettings(p => ({ ...p, username: v }))} placeholder="Your SMTP username" />
                  <Field label="SMTP Password *" type="password" value={settings.password || ''} onChange={v => setSettings(p => ({ ...p, password: v }))} placeholder="Your SMTP password" />
                </div>
              )}
            </div>
          )}

          {settings.provider && (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">Bounce Forward Email <span className="text-gray-400 font-normal">(optional)</span></label>
              <input type="email" placeholder="admin@yourdomain.com"
                className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                value={settings.bounce_forward_email || ''}
                onChange={e => setSettings(p => ({ ...p, bounce_forward_email: e.target.value }))} />
              <p className="text-xs text-gray-400 mt-1">Forward bounce notifications to this address.</p>
            </div>
          )}
        </div>
      )}

      {/* Test connection result */}
      <InlineMsg msg={testMsg} />

      {/* Save result */}
      <InlineMsg msg={saveMsg} />

      {/* Action buttons */}
      <div className="flex items-center gap-3 flex-wrap">
        {(isHostedService ? settings.smtp_choice === 'client' : true) && settings.provider && (
          <button onClick={testConnection}
            disabled={testing || !settings.username || !settings.password || (settings.provider === 'amazonses' && !settings.ses_type)}
            className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed">
            {testing ? <><span className="animate-spin">↻</span> Testing…</> : '🧪 Test Connection'}
          </button>
        )}
        <button onClick={saveSettings} disabled={saving}
          className="flex items-center gap-2 px-6 py-2.5 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 disabled:opacity-50 ml-auto">
          {saving ? <><span className="animate-spin">↻</span> Saving…</> : '💾 Save Configuration'}
        </button>
      </div>
    </div>
  );
}

// ─── tiny field helper ───────────────────────────────────────
function Field({ label, value, onChange, placeholder, type = 'text' }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1.5">{label}</label>
      <input type={type} value={value} onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
    </div>
  );
}

function InlineMsg({ msg }) {
  if (!msg) return null;
  return (
    <div className={`flex items-center gap-2 px-4 py-3 rounded-lg text-sm font-medium ${msg.type === 'success' ? 'bg-green-50 border border-green-200 text-green-800' : 'bg-red-50 border border-red-200 text-red-800'}`}>
      {msg.type === 'success' ? '✓' : '✕'} {msg.text}
    </div>
  );
}