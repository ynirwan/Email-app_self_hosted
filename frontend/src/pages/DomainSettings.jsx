// frontend/src/pages/DomainSettings.jsx
import { Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import API from '../api';

export default function DomainSettings() {
  const [domains, setDomains] = useState([]);
  const [newDomain, setNewDomain] = useState('');
  const [loading, setLoading] = useState(false);
  const [verificationDetails, setVerificationDetails] = useState(null);
  const [selectedDomain, setSelectedDomain] = useState(null);

  useEffect(() => {
    fetchDomains();
  }, []);

  const fetchDomains = async () => {
    try {
      const response = await API.get(`/domains`);
      // Add safety check to ensure response.data is an array
      const domainsData = Array.isArray(response.data) ? response.data : [];
      setDomains(domainsData);
      console.log('Fetched domains:', domainsData); // Debug log
    } catch (error) {
      console.error('Error fetching domains:', error);
      // Set empty array on error to prevent map error
      setDomains([]);
    }
  };

  const addDomain = async () => {
    if (!newDomain.trim()) return;

    setLoading(true);
    try {
      console.log('Adding domain:', newDomain.trim().toLowerCase());
      const response = await API.post(`/domains`, {
        domain: newDomain.trim().toLowerCase()
      });

      console.log('Add domain response:', response.data);
      
      // Ensure domains is always an array before spreading
      setDomains(prevDomains => [...(Array.isArray(prevDomains) ? prevDomains : []), response.data]);
      setNewDomain('');
      setVerificationDetails(response.data.verification_records);
      setSelectedDomain(response.data);
    } catch (error) {
      console.error('Error adding domain:', error);
      console.error('Error response:', error.response?.data);
      console.error('Error status:', error.response?.status);
      
      // Show more specific error message if available
      const errorMessage = error.response?.data?.detail || error.response?.data?.message || 'Failed to add domain. Please try again.';
      alert(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const verifyDomain = async (domainId) => {
    setLoading(true);
    try {
      const response = await API.post(`/domains/${domainId}/verify`);

      // Update the domain in the list with safety check
      setDomains(prevDomains =>
        Array.isArray(prevDomains)
          ? prevDomains.map(d => d.id === domainId ? { ...d, status: response.data.status } : d)
          : []
      );

      if (response.data.status === 'verified') {
        alert('Domain verified successfully!');
      } else {
        alert('Domain verification failed. Please check your DNS records and try again.');
      }
    } catch (error) {
      console.error('Error verifying domain:', error);
      alert('Verification failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const deleteDomain = async (domainId) => {
    if (!confirm('Are you sure you want to delete this domain?')) return;

    try {
      await API.delete(`/domains/${domainId}`);
      // Filter with safety check
      setDomains(prevDomains =>
        Array.isArray(prevDomains)
          ? prevDomains.filter(d => d.id !== domainId)
          : []
      );
    } catch (error) {
      console.error('Error deleting domain:', error);
      alert('Failed to delete domain. Please try again.');
    }
  };

  const showVerificationDetails = async (domain) => {
    try {
      const response = await API.get(`/domains/${domain.id}/verification-records`);
      setVerificationDetails(response.data.verification_records);
      setSelectedDomain(domain);
    } catch (error) {
      console.error('Error fetching verification details:', error);
    }
  };

  const getStatusBadge = (status) => {
    const statusStyles = {
      pending: 'bg-yellow-100 text-yellow-800',
      verified: 'bg-green-100 text-green-800',
      failed: 'bg-red-100 text-red-800'
    };

    return (
      <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusStyles[status]}`}>
        {status.charAt(0).toUpperCase() + status.slice(1)}
      </span>
    );
  };

  // Safety check before rendering
  const safeDomainsArray = Array.isArray(domains) ? domains : [];

  return (
    <div className="space-y-8">
      <h2 className="text-2xl font-bold">🌐 Domain Settings</h2>

      {/* Top Navigation Buttons */}
      <div className="flex gap-4 mb-6">
        <Link
          to="/settings/email"
          className="px-4 py-2 rounded-lg bg-gray-200 hover:bg-gray-300"
        >
          📧 Email Settings
        </Link>
        <Link
          to="/settings/domain"
          className="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700"
        >
          🌐 Domain Settings
        </Link>
      </div>

      {/* Domain List */}
      <div className="bg-white p-6 rounded-lg shadow">
        <h3 className="text-lg font-semibold mb-4">Your Domains</h3>
        {safeDomainsArray.length === 0 ? (
          <p className="text-gray-500 text-center py-8">No domains added yet. Add your first domain below.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border">
              <thead>
                <tr className="bg-gray-100 text-left">
                  <th className="p-3 border">Domain</th>
                  <th className="p-3 border">Status</th>
                  <th className="p-3 border">Added</th>
                  <th className="p-3 border">Actions</th>
                </tr>
              </thead>
              <tbody>
                {safeDomainsArray.map((domain) => (
                  <tr key={domain.id} className="hover:bg-gray-50">
                    <td className="p-3 border font-medium">{domain.domain}</td>
                    <td className="p-3 border">{getStatusBadge(domain.status)}</td>
                    <td className="p-3 border text-sm text-gray-600">
                      {new Date(domain.created_at).toLocaleDateString()}
                    </td>
                    <td className="p-3 border">
                      <div className="flex gap-2">
                        {domain.status === 'pending' && (
                          <>
                            <button
                              onClick={() => showVerificationDetails(domain)}
                              className="px-3 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700"
                            >
                              View Records
                            </button>
                            <button
                              onClick={() => verifyDomain(domain.id)}
                              disabled={loading}
                              className="px-3 py-1 bg-green-600 text-white text-xs rounded hover:bg-green-700 disabled:opacity-50"
                            >
                              Verify
                            </button>
                          </>
                        )}
                        {domain.status === 'failed' && (
                          <button
                            onClick={() => verifyDomain(domain.id)}
                            disabled={loading}
                            className="px-3 py-1 bg-orange-600 text-white text-xs rounded hover:bg-orange-700 disabled:opacity-50"
                          >
                            Retry
                          </button>
                        )}
                        <button
                          onClick={() => deleteDomain(domain.id)}
                          className="px-3 py-1 bg-red-600 text-white text-xs rounded hover:bg-red-700"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add New Domain */}
      <div className="bg-white p-6 rounded-lg shadow">
        <h3 className="text-lg font-semibold mb-4">Add New Domain</h3>
        <div className="flex gap-4">
          <input
            type="text"
            placeholder="Enter domain (e.g., example.com)"
            value={newDomain}
            onChange={(e) => setNewDomain(e.target.value)}
            className="flex-1 p-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            onKeyPress={(e) => e.key === 'Enter' && addDomain()}
          />
          <button
            onClick={addDomain}
            disabled={loading || !newDomain.trim()}
            className="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? '⏳ Adding...' : '➕ Add Domain'}
          </button>
        </div>
      </div>

      {/* Verification Details Modal/Panel */}
      {verificationDetails && selectedDomain && (
        <div className="bg-white p-6 rounded-lg shadow border-l-4 border-blue-500">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold">DNS Verification Records for {selectedDomain.domain}</h3>
            <button
              onClick={() => {
                setVerificationDetails(null);
                setSelectedDomain(null);
              }}
              className="text-gray-500 hover:text-gray-700"
            >
              ✕
            </button>
          </div>

          <div className="space-y-6">
            <div className="bg-yellow-50 p-4 rounded-lg border border-yellow-200">
              <p className="text-sm text-yellow-800 mb-2">
                <strong>⚠️ Important:</strong> Add these DNS records to your domain's DNS settings to verify ownership.
              </p>
            </div>

            {/* SPF Record */}
            <div className="bg-gray-50 p-4 rounded-lg">
              <h4 className="font-semibold mb-2 text-gray-800">📧 SPF Record (TXT)</h4>
              <div className="space-y-2 text-sm">
                <div><strong>Name:</strong> @ (or leave blank)</div>
                <div><strong>Type:</strong> TXT</div>
                <div><strong>Value:</strong>
                  <code className="bg-white px-2 py-1 rounded ml-2 break-all">
                    {verificationDetails.spf_record}
                  </code>
                </div>
              </div>
            </div>

            {/* DKIM Record */}
            <div className="bg-gray-50 p-4 rounded-lg">
              <h4 className="font-semibold mb-2 text-gray-800">🔐 DKIM Record (TXT)</h4>
              <div className="space-y-2 text-sm">
                <div><strong>Name:</strong>
                  <code className="bg-white px-2 py-1 rounded ml-2">
                    {verificationDetails.dkim_selector}._domainkey
                  </code>
                </div>
                <div><strong>Type:</strong> TXT</div>
                <div><strong>Value:</strong>
                  <code className="bg-white px-2 py-1 rounded ml-2 break-all text-xs">
                    {verificationDetails.dkim_record}
                  </code>
                </div>
              </div>
            </div>

            {/* DMARC Record */}
            <div className="bg-gray-50 p-4 rounded-lg">
              <h4 className="font-semibold mb-2 text-gray-800">🛡️ DMARC Record (TXT)</h4>
              <div className="space-y-2 text-sm">
                <div><strong>Name:</strong>
                  <code className="bg-white px-2 py-1 rounded ml-2">_dmarc</code>
                </div>
                <div><strong>Type:</strong> TXT</div>
                <div><strong>Value:</strong>
                  <code className="bg-white px-2 py-1 rounded ml-2 break-all">
                    {verificationDetails.dmarc_record}
                  </code>
                </div>
              </div>
            </div>

            {/* Verification Record */}
            <div className="bg-gray-50 p-4 rounded-lg">
              <h4 className="font-semibold mb-2 text-gray-800">✅ Domain Verification (TXT)</h4>
              <div className="space-y-2 text-sm">
                <div><strong>Name:</strong>
                  <code className="bg-white px-2 py-1 rounded ml-2">
                    _emailverify
                  </code>
                </div>
                <div><strong>Type:</strong> TXT</div>
                <div><strong>Value:</strong>
                  <code className="bg-white px-2 py-1 rounded ml-2 break-all">
                    {verificationDetails.verification_token}
                  </code>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
            <p className="text-sm text-blue-800">
              <strong>💡 Next Steps:</strong>
            </p>
            <ol className="text-sm text-blue-700 mt-2 space-y-1 list-decimal list-inside">
              <li>Add all the DNS records above to your domain's DNS settings</li>
              <li>Wait for DNS propagation (usually 5-30 minutes)</li>
              <li>Click the "Verify" button to check if the records are properly configured</li>
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}
