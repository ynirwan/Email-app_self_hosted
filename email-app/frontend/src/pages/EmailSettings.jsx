// frontend/src/pages/EmailSettings.jsx
// Email settings page with support for Managed SMTP, SES API, and SES SMTP

import { useState, useEffect } from 'react';
import API from '../api';

export default function EmailSettings() {
  const [systemInfo, setSystemInfo] = useState(null);
  const [settings, setSettings] = useState({
    smtp_choice: 'managed',
    provider: '',
    smtp_server: '',
    smtp_port: 587,
    username: '',
    password: '',
    ses_type: null,
    aws_region: 'us-east-1',
    bounce_forward_email: ''
  });
  const [usage, setUsage] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [loading, setLoading] = useState(true);

  const isHostedService = systemInfo?.deployment_mode === 'hosted_service';

  // Provider configurations
  const providerConfigs = {
    sendgrid: {
      name: 'SendGrid',
      smtp_server: 'smtp.sendgrid.net',
      smtp_port: 587,
      usernameLabel: 'API Key',
      passwordLabel: 'Password (or use API key again)',
      helpText: 'Use your SendGrid API key as both username and password'
    },
    mailgun: {
      name: 'Mailgun',
      smtp_server: 'smtp.mailgun.org',
      smtp_port: 587,
      usernameLabel: 'Username',
      passwordLabel: 'Password',
      helpText: 'Get SMTP credentials from Mailgun dashboard'
    },
    postmark: {
      name: 'Postmark',
      smtp_server: 'smtp.postmarkapp.com',
      smtp_port: 587,
      usernameLabel: 'Server API Token',
      passwordLabel: 'Server API Token',
      helpText: 'Use the same Server API Token for both fields'
    },
    custom: {
      name: 'Custom SMTP',
      smtp_server: '',
      smtp_port: 587,
      usernameLabel: 'Username',
      passwordLabel: 'Password',
      helpText: 'Configure your custom SMTP server'
    }
  };

  // AWS Regions for SES
  const awsRegions = [
    { value: 'us-east-1', label: 'US East (N. Virginia)' },
    { value: 'us-west-2', label: 'US West (Oregon)' },
    { value: 'eu-west-1', label: 'Europe (Ireland)' },
    { value: 'eu-central-1', label: 'Europe (Frankfurt)' },
    { value: 'ap-south-1', label: 'Asia Pacific (Mumbai)' },
    { value: 'ap-southeast-1', label: 'Asia Pacific (Singapore)' },
    { value: 'ap-southeast-2', label: 'Asia Pacific (Sydney)' },
    { value: 'ap-northeast-1', label: 'Asia Pacific (Tokyo)' },
  ];

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
        try {
          const usageResponse = await API.get('/email/usage');
          setUsage(usageResponse.data);
        } catch (err) {
          console.log('Usage data not available');
        }
      }
    } catch (err) {
      console.error('Failed to fetch data:', err);
      alert('Failed to load email settings');
    } finally {
      setLoading(false);
    }
  };

  const handleProviderChange = (provider) => {
    const config = providerConfigs[provider];

    if (provider === 'amazonses') {
      // For SES, don't auto-fill SMTP server yet - user needs to choose API or SMTP
      setSettings(prev => ({
        ...prev,
        provider: 'amazonses',
        ses_type: null,  // Force user to select
        smtp_server: '',
        smtp_port: 587,
        aws_region: 'us-east-1'
      }));
    } else if (config) {
      setSettings(prev => ({
        ...prev,
        provider,
        smtp_server: config.smtp_server,
        smtp_port: config.smtp_port,
        ses_type: null
      }));
    }
  };

  const handleSESTypeChange = (sesType) => {
    if (sesType === 'api') {
      setSettings(prev => ({
        ...prev,
        ses_type: 'api',
        smtp_server: '',  // Not needed for API
        smtp_port: 587
      }));
    } else if (sesType === 'smtp') {
      setSettings(prev => ({
        ...prev,
        ses_type: 'smtp',
        smtp_server: `email-smtp.${prev.aws_region}.amazonaws.com`,
        smtp_port: 587
      }));
    }
  };

  const handleAWSRegionChange = (region) => {
    setSettings(prev => ({
      ...prev,
      aws_region: region,
      // Update SMTP server if using SES SMTP
      smtp_server: prev.ses_type === 'smtp'
        ? `email-smtp.${region}.amazonaws.com`
        : prev.smtp_server
    }));
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
      const response = await API.post('/email/test-connection', {
        provider: settings.provider,
        smtp_server: settings.smtp_server,
        smtp_port: settings.smtp_port,
        username: settings.username,
        password: settings.password,
        ses_type: settings.ses_type,
        aws_region: settings.aws_region
      });
      alert(response.data.message);
    } catch (err) {
      console.error('Test error:', err);
      alert(`❌ Connection test failed: ${err.response?.data?.detail || 'Unknown error'}`);
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-xl">Loading email settings...</div>
      </div>
    );
  }

  const currentProviderConfig = providerConfigs[settings.provider] || providerConfigs.custom;

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      <h1 className="text-3xl font-bold mb-6">📧 Email Configuration</h1>

      {/* Deployment Info */}
      <div className="bg-blue-50 border border-blue-200 p-4 rounded-lg">
        <p className="text-blue-800">
          <strong>Deployment Mode:</strong> {isHostedService ? '☁️ Hosted Service' : '🏠 Self-Hosted'}
        </p>
        <p className="text-sm text-blue-600 mt-1">
          {isHostedService
            ? 'Managed infrastructure with quota enforced per your subscription plan.'
            : 'Self-hosted deployment with full control over email sending.'}
        </p>
      </div>

      {/* SMTP Choice (Hosted Service Only) */}
      {isHostedService && (
        <div className="bg-white p-6 rounded-lg shadow-lg">
          <h2 className="text-xl font-semibold mb-6">📨 SMTP Configuration Type</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Managed SMTP */}
            <div
              className={`p-6 border-2 rounded-lg cursor-pointer transition-all ${settings.smtp_choice === 'managed'
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
                <li className="flex items-center">
                  <span className="text-green-500 mr-2">✓</span>
                  High deliverability
                </li>
                <li className="flex items-center">
                  <span className="text-green-500 mr-2">✓</span>
                  Managed infrastructure
                </li>
                <li className="flex items-center">
                  <span className="text-green-500 mr-2">✓</span>
                  Quota based on plan
                </li>
              </ul>
            </div>

            {/* Your SMTP */}
            <div
              className={`p-6 border-2 rounded-lg cursor-pointer transition-all ${settings.smtp_choice === 'client'
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
                <li className="flex items-center">
                  <span className="text-blue-500 mr-2">✓</span>
                  Use your own provider
                </li>
                <li className="flex items-center">
                  <span className="text-blue-500 mr-2">✓</span>
                  Full control
                </li>
                <li className="flex items-center">
                  <span className="text-blue-500 mr-2">✓</span>
                  No additional cost
                </li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Provider Selection (Client SMTP) */}
      {isHostedService && settings.smtp_choice === 'client' && (
        <div className="bg-white p-6 rounded-lg shadow-lg">
          <h2 className="text-xl font-semibold mb-6">🔧 Email Provider</h2>
          <div className="mb-6">
            <label className="block text-sm font-medium mb-2">Select Email Provider</label>
            <select
              className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
              value={settings.provider || ''}
              onChange={(e) => handleProviderChange(e.target.value)}
            >
              <option value="">Choose Provider</option>
              <option value="amazonses">🟠 Amazon SES (API or SMTP)</option>
              <option value="sendgrid">SendGrid</option>
              <option value="mailgun">Mailgun</option>
              <option value="postmark">Postmark</option>
              <option value="custom">Custom SMTP</option>
            </select>
          </div>

          {/* Amazon SES Type Selection */}
          {settings.provider === 'amazonses' && (
            <div className="mb-6 p-4 bg-orange-50 border border-orange-200 rounded-lg">
              <h3 className="text-lg font-semibold mb-4">🟠 Amazon SES Configuration</h3>
              <p className="text-sm text-gray-600 mb-4">
                Amazon SES supports two authentication methods. Choose one:
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* SES API */}
                <div
                  className={`p-4 border-2 rounded-lg cursor-pointer transition-all ${settings.ses_type === 'api'
                      ? 'border-orange-500 bg-orange-50'
                      : 'border-gray-300 hover:border-orange-400'
                    }`}
                  onClick={() => handleSESTypeChange('api')}
                >
                  <div className="flex items-center mb-2">
                    <input
                      type="radio"
                      checked={settings.ses_type === 'api'}
                      readOnly
                      className="mr-2"
                    />
                    <h4 className="font-semibold">SES API (boto3)</h4>
                  </div>
                  <p className="text-xs text-gray-600">Use IAM Access Key + Secret Key</p>
                  <ul className="text-xs text-gray-600 mt-2 space-y-1">
                    <li>• More features (quota checking)</li>
                    <li>• Better error handling</li>
                    <li>• Requires boto3 library</li>
                  </ul>
                </div>

                {/* SES SMTP */}
                <div
                  className={`p-4 border-2 rounded-lg cursor-pointer transition-all ${settings.ses_type === 'smtp'
                      ? 'border-orange-500 bg-orange-50'
                      : 'border-gray-300 hover:border-orange-400'
                    }`}
                  onClick={() => handleSESTypeChange('smtp')}
                >
                  <div className="flex items-center mb-2">
                    <input
                      type="radio"
                      checked={settings.ses_type === 'smtp'}
                      readOnly
                      className="mr-2"
                    />
                    <h4 className="font-semibold">SES SMTP</h4>
                  </div>
                  <p className="text-xs text-gray-600">Use SMTP username + password</p>
                  <ul className="text-xs text-gray-600 mt-2 space-y-1">
                    <li>• Standard SMTP protocol</li>
                    <li>• Generated from IAM credentials</li>
                    <li>• Easier to set up</li>
                  </ul>
                </div>
              </div>

              {/* AWS Region Selection */}
              <div className="mt-4">
                <label className="block text-sm font-medium mb-2">AWS Region</label>
                <select
                  className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-orange-500"
                  value={settings.aws_region}
                  onChange={(e) => handleAWSRegionChange(e.target.value)}
                >
                  {awsRegions.map(region => (
                    <option key={region.value} value={region.value}>
                      {region.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* Credentials Form */}
          {settings.provider && settings.provider !== 'amazonses' ? (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">🔐 {currentProviderConfig.name} Credentials</h3>
              <p className="text-sm text-gray-600 mb-4">{currentProviderConfig.helpText}</p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium mb-2">SMTP Server *</label>
                  <input
                    type="text"
                    className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                    value={settings.smtp_server || ''}
                    onChange={(e) => setSettings(prev => ({ ...prev, smtp_server: e.target.value }))}
                    placeholder="smtp.provider.com"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Port *</label>
                  <select
                    className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                    value={settings.smtp_port || 587}
                    onChange={(e) => setSettings(prev => ({ ...prev, smtp_port: parseInt(e.target.value) }))}
                  >
                    <option value={587}>587 (STARTTLS)</option>
                    <option value={465}>465 (SSL)</option>
                    <option value={25}>25 (Plain)</option>
                    <option value={2525}>2525 (Alternative)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">{currentProviderConfig.usernameLabel} *</label>
                  <input
                    type="text"
                    className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                    value={settings.username || ''}
                    onChange={(e) => setSettings(prev => ({ ...prev, username: e.target.value }))}
                    placeholder={currentProviderConfig.usernameLabel}
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">{currentProviderConfig.passwordLabel} *</label>
                  <input
                    type="password"
                    className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                    value={settings.password || ''}
                    onChange={(e) => setSettings(prev => ({ ...prev, password: e.target.value }))}
                    placeholder={currentProviderConfig.passwordLabel}
                    required
                  />
                </div>
              </div>
            </div>
          ) : settings.provider === 'amazonses' && settings.ses_type ? (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">
                🔐 Amazon SES {settings.ses_type === 'api' ? 'API' : 'SMTP'} Credentials
              </h3>

              {settings.ses_type === 'api' ? (
                <>
                  <p className="text-sm text-gray-600 mb-4">
                    Enter your IAM user's Access Key ID and Secret Access Key.
                    <a href="https://docs.aws.amazon.com/ses/latest/dg/create-shared-credentials.html"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline ml-1">
                      Learn more →
                    </a>
                  </p>
                  <div className="grid grid-cols-1 gap-6">
                    <div>
                      <label className="block text-sm font-medium mb-2">AWS Access Key ID *</label>
                      <input
                        type="text"
                        className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-orange-500"
                        value={settings.username || ''}
                        onChange={(e) => setSettings(prev => ({ ...prev, username: e.target.value }))}
                        placeholder="AKIAIOSFODNN7EXAMPLE"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2">AWS Secret Access Key *</label>
                      <input
                        type="password"
                        className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-orange-500"
                        value={settings.password || ''}
                        onChange={(e) => setSettings(prev => ({ ...prev, password: e.target.value }))}
                        placeholder="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
                        required
                      />
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <p className="text-sm text-gray-600 mb-4">
                    Enter your SMTP username and password generated from your IAM credentials.
                    <a href="https://docs.aws.amazon.com/ses/latest/dg/smtp-credentials.html"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline ml-1">
                      Learn more →
                    </a>
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <label className="block text-sm font-medium mb-2">SMTP Server (Auto-filled)</label>
                      <input
                        type="text"
                        className="w-full p-3 border rounded-lg bg-gray-100"
                        value={settings.smtp_server}
                        readOnly
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2">Port</label>
                      <select
                        className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-orange-500"
                        value={settings.smtp_port || 587}
                        onChange={(e) => setSettings(prev => ({ ...prev, smtp_port: parseInt(e.target.value) }))}
                      >
                        <option value={587}>587 (STARTTLS)</option>
                        <option value={465}>465 (SSL)</option>
                        <option value={25}>25 (Plain)</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2">SMTP Username *</label>
                      <input
                        type="text"
                        className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-orange-500"
                        value={settings.username || ''}
                        onChange={(e) => setSettings(prev => ({ ...prev, username: e.target.value }))}
                        placeholder="Your SMTP username"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2">SMTP Password *</label>
                      <input
                        type="password"
                        className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-orange-500"
                        value={settings.password || ''}
                        onChange={(e) => setSettings(prev => ({ ...prev, password: e.target.value }))}
                        placeholder="Your SMTP password"
                        required
                      />
                    </div>
                  </div>
                </>
              )}
            </div>
          ) : null}

          {/* Bounce Forward Email */}
          {settings.provider && (
            <div className="mt-6">
              <label className="block text-sm font-medium mb-2">Bounce Forward Email (Optional)</label>
              <input
                type="email"
                className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                value={settings.bounce_forward_email || ''}
                onChange={(e) => setSettings(prev => ({ ...prev, bounce_forward_email: e.target.value }))}
                placeholder="admin@yourdomain.com"
              />
              <p className="text-xs text-gray-500 mt-1">
                Forward bounce notifications to this email address.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex justify-between items-center">
        {isHostedService && settings.smtp_choice === 'client' && settings.provider && (
          <button
            onClick={testConnection}
            disabled={testing || !settings.username || !settings.password ||
              (settings.provider === 'amazonses' && !settings.ses_type)}
            className={`px-6 py-3 rounded-lg font-medium transition-all ${testing || !settings.username || !settings.password ||
                (settings.provider === 'amazonses' && !settings.ses_type)
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700 shadow-lg hover:shadow-xl'
              }`}
          >
            {testing ? '🔄 Testing...' : '🧪 Test Connection'}
          </button>
        )}
        <div className="flex gap-4 ml-auto">
          <button
            onClick={saveSettings}
            disabled={saving}
            className={`px-8 py-3 rounded-lg font-medium transition-all ${saving
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