import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import API from '../api';

const ABTestingDashboard = () => {
  const [abTests, setAbTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState({});
  const [resultsModal, setResultsModal] = useState(null);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const fetchData = async () => {
    try {
      setLoading(true);
      setError('');

      const testsRes = await API.get('/ab-tests');
      setAbTests(testsRes.data.tests || testsRes.data || []);

    } catch (err) {
      console.error('Failed to fetch data:', err);
      setError('Failed to load dashboard data');
      setAbTests([]);
    } finally {
      setLoading(false);
    }
  };

  const startTest = async (testId) => {
    try {
      setActionLoading(prev => ({ ...prev, [testId]: 'starting' }));
      await API.post(`/ab-tests/${testId}/start`);
      alert('A/B test started successfully!');
      fetchData();
    } catch (err) {
      alert('Failed to start test: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(prev => ({ ...prev, [testId]: null }));
    }
  };

  const stopTest = async (testId) => {
    if (!window.confirm('Are you sure you want to stop this test?')) return;
    try {
      setActionLoading(prev => ({ ...prev, [testId]: 'stopping' }));
      await API.post(`/ab-tests/${testId}/stop`);
      alert('A/B test stopped successfully!');
      fetchData();
    } catch (err) {
      alert('Failed to stop test: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(prev => ({ ...prev, [testId]: null }));
    }
  };

  const deleteTest = async (testId) => {
    if (!window.confirm('Are you sure you want to delete this test? This action cannot be undone.')) return;
    try {
      setActionLoading(prev => ({ ...prev, [testId]: 'deleting' }));
      await API.delete(`/ab-tests/${testId}`);
      alert('A/B test deleted successfully!');
      fetchData();
    } catch (err) {
      alert('Failed to delete test: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(prev => ({ ...prev, [testId]: null }));
    }
  };

  const viewResults = async (testId) => {
    try {
      setActionLoading(prev => ({ ...prev, [testId]: 'loading' }));
      const response = await API.get(`/ab-tests/${testId}/results`);
      setResultsModal(response.data);
    } catch (err) {
      alert('Error fetching results: ' + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(prev => ({ ...prev, [testId]: null }));
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto mt-10 p-6">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading A/B testing dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">A/B Testing</h1>
        <button
          onClick={() => navigate('/ab-testing/create')}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
        >
          + Create A/B Test
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-purple-50 p-6 rounded-lg border">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-purple-600 font-medium">Active Tests</p>
              <p className="text-3xl font-bold text-purple-800">
                {abTests.filter(t => t.status === 'running').length}
              </p>
            </div>
            <span className="text-4xl">🏃</span>
          </div>
        </div>

        <div className="bg-blue-50 p-6 rounded-lg border">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-blue-600 font-medium">Draft Tests</p>
              <p className="text-3xl font-bold text-blue-800">
                {abTests.filter(t => t.status === 'draft').length}
              </p>
            </div>
            <span className="text-4xl">📝</span>
          </div>
        </div>

        <div className="bg-green-50 p-6 rounded-lg border">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-green-600 font-medium">Completed Tests</p>
              <p className="text-3xl font-bold text-green-800">
                {abTests.filter(t => t.status === 'completed').length}
              </p>
            </div>
            <span className="text-4xl">✅</span>
          </div>
        </div>
      </div>

      {/* A/B Tests List */}
      <div>
        <h2 className="text-xl font-semibold mb-4">Your A/B Tests</h2>
        {abTests.length === 0 ? (
          <div className="bg-gray-50 p-12 text-center rounded-lg">
            <p className="text-gray-600 mb-4 text-lg">No A/B tests created yet</p>
            <p className="text-gray-500 mb-6">Create your first test to start optimizing your email campaigns</p>
            <button
              onClick={() => navigate('/ab-testing/create')}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
            >
              + Create Your First A/B Test
            </button>
          </div>
        ) : (
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Test Name</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Lists</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Sample Size</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {abTests.map(test => (
                  <tr key={test._id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 font-medium text-gray-900">{test.test_name}</td>
                    <td className="px-6 py-4">
                      <span className="bg-gray-100 px-2 py-1 rounded text-sm">
                        {test.test_type.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {(test.target_lists || []).join(', ') || '-'}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded text-sm font-medium ${
                        test.status === 'running' ? 'bg-blue-100 text-blue-800' :
                        test.status === 'completed' ? 'bg-green-100 text-green-800' :
                        test.status === 'failed' ? 'bg-red-100 text-red-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {test.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-gray-600">{test.sample_size}</td>
                    <td className="px-6 py-4">
                      <div className="flex space-x-2">
                        {test.status === 'draft' && (
                          <button
                            onClick={() => startTest(test._id)}
                            disabled={actionLoading[test._id] === 'starting'}
                            className="text-green-600 hover:underline text-sm disabled:opacity-50"
                          >
                            {actionLoading[test._id] === 'starting' ? 'Starting...' : 'Start'}
                          </button>
                        )}

                        {test.status === 'running' && (
                          <button
                            onClick={() => stopTest(test._id)}
                            disabled={actionLoading[test._id] === 'stopping'}
                            className="text-red-600 hover:underline text-sm disabled:opacity-50"
                          >
                            {actionLoading[test._id] === 'stopping' ? 'Stopping...' : 'Stop'}
                          </button>
                        )}

                        {(test.status === 'running' || test.status === 'completed') && (
                          <button
                            onClick={() => viewResults(test._id)}
                            disabled={actionLoading[test._id] === 'loading'}
                            className="text-purple-600 hover:underline text-sm disabled:opacity-50"
                          >
                            {actionLoading[test._id] === 'loading' ? 'Loading...' : 'Results'}
                          </button>
                        )}

                        <button
                          onClick={() => deleteTest(test._id)}
                          disabled={actionLoading[test._id] === 'deleting'}
                          className="text-red-600 hover:underline text-sm disabled:opacity-50"
                        >
                          {actionLoading[test._id] === 'deleting' ? 'Deleting...' : 'Delete'}
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

      {/* Results Modal */}
      {resultsModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-2xl font-bold">Quick Results Summary</h3>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => {
                    setResultsModal(null);
                    navigate(`/ab-tests/${resultsModal.test_id}/results`);
                  }}
                  className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 text-sm"
                >
                  Open Full Report
                </button>
                <button
                  onClick={() => setResultsModal(null)}
                  className="text-gray-400 hover:text-gray-600 text-2xl font-bold"
                >
                  x
                </button>
              </div>
            </div>

            <div className="space-y-6">
              <div className="bg-gray-50 p-4 rounded-lg">
                <h4 className="font-semibold mb-2">{resultsModal.test_name}</h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <p className="text-gray-600">Status</p>
                    <p className="font-bold">{resultsModal.status}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Test Type</p>
                    <p className="font-bold">{resultsModal.test_type.replace('_', ' ')}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Sample Size</p>
                    <p className="font-bold">{resultsModal.sample_size}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Target Lists</p>
                    <p className="font-bold">{(resultsModal.target_lists || []).join(', ')}</p>
                  </div>
                </div>
              </div>

              {resultsModal.winner.winner !== "TIE" && (
                <div className="bg-green-50 border-2 border-green-300 rounded-lg p-4">
                  <p className="text-lg font-bold text-green-800">
                    Variant {resultsModal.winner.winner} is winning by {resultsModal.winner.improvement.toFixed(2)}%
                  </p>
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-100">
                    <tr>
                      <th className="px-4 py-3 text-left">Variant</th>
                      <th className="px-4 py-3 text-right">Sent</th>
                      <th className="px-4 py-3 text-right">Opened</th>
                      <th className="px-4 py-3 text-right">Open Rate</th>
                      <th className="px-4 py-3 text-right">Clicked</th>
                      <th className="px-4 py-3 text-right">Click Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-t">
                      <td className="px-4 py-3 font-semibold">Variant A</td>
                      <td className="px-4 py-3 text-right">{resultsModal.results.variant_a.sent}</td>
                      <td className="px-4 py-3 text-right">{resultsModal.results.variant_a.opened}</td>
                      <td className="px-4 py-3 text-right">{resultsModal.results.variant_a.open_rate.toFixed(2)}%</td>
                      <td className="px-4 py-3 text-right">{resultsModal.results.variant_a.clicked}</td>
                      <td className="px-4 py-3 text-right">{resultsModal.results.variant_a.click_rate.toFixed(2)}%</td>
                    </tr>
                    <tr className="border-t bg-gray-50">
                      <td className="px-4 py-3 font-semibold">Variant B</td>
                      <td className="px-4 py-3 text-right">{resultsModal.results.variant_b.sent}</td>
                      <td className="px-4 py-3 text-right">{resultsModal.results.variant_b.opened}</td>
                      <td className="px-4 py-3 text-right">{resultsModal.results.variant_b.open_rate.toFixed(2)}%</td>
                      <td className="px-4 py-3 text-right">{resultsModal.results.variant_b.clicked}</td>
                      <td className="px-4 py-3 text-right">{resultsModal.results.variant_b.click_rate.toFixed(2)}%</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="bg-blue-50 p-4 rounded-lg">
                <p className="font-semibold mb-2">Statistical Significance</p>
                <p className="text-sm text-gray-700">
                  Confidence Level: <span className="font-bold uppercase">{resultsModal.statistical_significance.confidence_level}</span>
                </p>
                <p className="text-sm text-gray-700">
                  Total Samples: <span className="font-bold">{resultsModal.statistical_significance.total_samples}</span>
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ABTestingDashboard;
