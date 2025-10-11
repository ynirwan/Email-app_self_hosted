// frontend/src/pages/EmailSettings.jsx
import { useState, useEffect } from 'react';
import API from '../api';

export default function EmailSettings() {
  const [systemInfo, setSystemInfo] = useState(null);
  const [settings, setSettings] = useState({});
  const [usage, setUsage] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [loading, setLoading] = useState(true);

  const isHostedService = systemInfo?.deployment_mode === 'hosted_service';

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [systemResponse, settingsResponse] = await Promise.all([
        API.get('/email/system-info'),
        API.get('/email/settings')
      ]);
      setSystemInfo(systemResponse.data);
      setSettings(settingsResponse.data);

      if (systemResponse.data.deployment_mode === 'hosted_service') {
        const usageResponse = await API.get('/email/usage');
        setUsage(usageResponse.data);
      }
    } catch (err) {
      console.error('Failed to fetch data:', err);
      alert('Failed to load email settings');
    } finally {
      setLoading(false);
    }
  };

  const handleProviderChange = (provider) => {
    const providerConfigs = {
      sendgrid: {
        smtp_server: 'smtp.sendgrid.net',
        smtp_port: 587
      },
      mailgun: {
        smtp_server: 'smtp.mailgun.org',
        smtp_port: 587
      },
      amazonses: {
        smtp_server: 'email-smtp.us-east-1.amazonaws.com',
        smtp_port: 587
      },
      postmark: {
        smtp_server: 'smtp.postmarkapp.com',
        smtp_port: 587
      }
    };
    const config = providerConfigs[provider];
    if (config) {
      setSettings(prev => ({
        ...prev,
        provider,
        smtp_server: config.smtp_server,
        smtp_port: config.smtp_port
      }));
    } else {
      setSettings(prev => ({
        ...prev,
        provider,
        smtp_server: '',
        smtp_port: 587
      }));
    }
  };

  const saveSettings = async () => {
    try {
      setSaving(true);
      await API.put('/email/settings', settings);
      alert('✅ Email settings saved successfully!');
      fetchData();
    } catch (err) {
      console.error('Save error:', err);
      alert(`❌ Failed to save: ${err.response?.data?.detail || 'Unknown error'}`);
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    try {
      setTesting(true);
      await API.post('/email/test-connection', {
        smtp_server: settings.smtp_server,
        smtp_port: settings.smtp_port,
        username: settings.username,
        password: settings.password
      });
      alert('✅ SMTP connection successful!');
    } catch (err) {
      console.error('Test error:', err);
      alert(`❌ Connection failed: ${err.response?.data?.detail || 'Unknown error'}`);
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-screen">
        <div className="text-lg">Loading email settings...</div>
      </div>
    );
  }

  const emailsRemaining = usage && usage.quota
    ? usage.quota.daily_limit - usage.quota.current_usage
    : 0;

  return (
    <div className="max-w-6xl mx-auto mt-10 space-y-8 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">📧 Email Configuration</h1>
        <div className="px-4 py-2 rounded-full text-sm font-medium bg-blue-100 text-blue-800">
          ☁️ Hosted Service
        </div>
      </div>

      {/* Quota Info */}
      <div className="bg-blue-100 p-4 rounded text-blue-800 font-semibold">
        ☁️ Hosted service benefit: {emailsRemaining.toLocaleString()} emails remaining today. Managed infrastructure with quota enforced per your subscription plan.
      </div>

      {/* SMTP Choice */}
      {isHostedService && (
        <div className="bg-white p-6 rounded-lg shadow-lg">
          <h2 className="text-xl font-semibold mb-6">📨 SMTP Configuration</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div
              className={`p-6 border-2 rounded-lg cursor-pointer transition-all ${
                settings.smtp_choice === 'managed'
                  ? 'border-green-500 bg-green-50'
                  : 'border-gray-200 hover:border-green-300'
              }`}
              onClick={() => setSettings(prev => ({ ...prev, smtp_choice: 'managed' }))}
            >
              <div className="flex items-center mb-3">
                <input
                  type="radio"
                  checked={settings.smtp_choice === 'managed'}
                  readOnly
                  className="mr-3"
                />
                <h3 className="text-lg font-semibold">🚀 Managed SMTP</h3>
              </div>
              <p className="text-gray-600 mb-4">Premium email service managed by us</p>
              <ul className="text-sm text-gray-600 space-y-2">
                {systemInfo.smtp_options?.managed?.features?.map((feature, index) => (
                  <li key={index} className="flex items-center">
                    <span className="text-green-500 mr-2">✓</span>
                    {feature}
                  </li>
                ))}
              </ul>
            </div>
            <div
              className={`p-6 border-2 rounded-lg cursor-pointer transition-all ${
                settings.smtp_choice === 'client'
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-blue-300'
              }`}
              onClick={() => setSettings(prev => ({ ...prev, smtp_choice: 'client' }))}
            >
              <div className="flex items-center mb-3">
                <input
                  type="radio"
                  checked={settings.smtp_choice === 'client'}
                  readOnly
                  className="mr-3"
                />
                <h3 className="text-lg font-semibold">⚙️ Your SMTP</h3>
              </div>
              <p className="text-gray-600 mb-4">Use your own SMTP provider</p>
              <ul className="text-sm text-gray-600 space-y-2">
                {systemInfo.smtp_options?.client?.features?.map((feature, index) => (
                  <li key={index} className="flex items-center">
                    <span className="text-blue-500 mr-2">✓</span>
                    {feature}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* SMTP Client Config Form */}
      {isHostedService && settings.smtp_choice === 'client' && (
        <div className="bg-white p-6 rounded-lg shadow-lg">
          <h2 className="text-xl font-semibold mb-6">🔧 SMTP Server Configuration</h2>
          <div className="mb-6">
            <label className="block text-sm font-medium mb-2">Email Provider</label>
            <select
              className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
              value={settings.provider || ''}
              onChange={(e) => handleProviderChange(e.target.value)}
            >
              <option value="">Select Provider</option>
              <option value="sendgrid">SendGrid</option>
              <option value="mailgun">Mailgun</option>
              <option value="amazonses">Amazon SES</option>
              <option value="postmark">Postmark</option>
              <option value="custom">Custom SMTP</option>
            </select>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium mb-2">SMTP Server *</label>
              <input
                type="text"
                className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                value={settings.smtp_server || ''}
                onChange={(e) => setSettings(prev => ({...prev, smtp_server: e.target.value}))}
                placeholder="smtp.provider.com"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Port *</label>
              <select
                className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                value={settings.smtp_port || 587}
                onChange={(e) => setSettings(prev => ({...prev, smtp_port: parseInt(e.target.value)}))}
              >
                <option value={587}>587 (STARTTLS)</option>
                <option value={465}>465 (SSL)</option>
                <option value={25}>25 (Plain)</option>
                <option value={2525}>2525 (Alternative)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Username *</label>
              <input
                type="text"
                className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                value={settings.username || ''}
                onChange={(e) => setSettings(prev => ({...prev, username: e.target.value}))}
                placeholder="API key or username"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Password/API Key *</label>
              <input
                type="password"
                className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                value={settings.password || ''}
                onChange={(e) => setSettings(prev => ({...prev, password: e.target.value}))}
                placeholder="Password or API key"
                required
              />
            </div>
          </div>
          <div className="mt-6">
            <label className="block text-sm font-medium mb-2">Bounce Forward Email</label>
            <input
              type="email"
              className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
              value={settings.bounce_forward_email || ''}
              onChange={(e) => setSettings(prev => ({...prev, bounce_forward_email: e.target.value}))}
              placeholder="admin@yourdomain.com"
            />
            <p className="text-xs text-gray-500 mt-1">
              Forward bounce notifications to this email.
            </p>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex justify-between items-center">
        {isHostedService && settings.smtp_choice === 'client' && (
          <button
            onClick={testConnection}
            disabled={testing || !settings.smtp_server || !settings.username || !settings.password}
            className={`px-6 py-3 rounded-lg font-medium transition-all ${
              testing || !settings.smtp_server || !settings.username || !settings.password
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700 shadow-lg hover:shadow-xl'
            }`}
          >
            {testing ? '🔄 Testing...' : '🧪 Test Connection'}
          </button>
        )}
        <div className="flex gap-4">
          <button
            onClick={saveSettings}
            disabled={saving}
            className={`px-8 py-3 rounded-lg font-medium transition-all ${
              saving
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-green-600 text-white hover:bg-green-700 shadow-lg hover:shadow-xl'
            }`}
          >
            {saving ? '💾 Saving...' : '💾 Save Configuration'}
          </button>
        </div>
      </div>
    </div>
  );
}

