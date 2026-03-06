import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import API from '../api';

const ABTestResults = () => {
  const { testId } = useParams();
  const navigate = useNavigate();
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchResults = async () => {
      try {
        const response = await API.get(`/ab-tests/${testId}/results`);
        setResults(response.data);
        setLoading(false);
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to load results');
        setLoading(false);
      }
    };

    fetchResults();
    // Refresh every 30 seconds for real-time updates
    const interval = setInterval(fetchResults, 30000);
    return () => clearInterval(interval);
  }, [testId]);

  if (loading) return (
    <div className="max-w-6xl mx-auto mt-10 p-6">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
        <p className="mt-4 text-gray-600">Loading results...</p>
      </div>
    </div>
  );

  if (error) return (
    <div className="max-w-6xl mx-auto mt-10 p-6">
      <div className="bg-red-50 border border-red-200 rounded p-4">
        <p className="text-red-800">{error}</p>
        <button
          onClick={() => navigate('/ab-testing')}
          className="text-red-600 underline mt-2"
        >
          ← Back to Dashboard
        </button>
      </div>
    </div>
  );

  if (!results) return null;

  const calculatePercentageDiff = (a, b) => {
    if (b === 0) return a > 0 ? 100 : 0;
    return ((a - b) / b * 100).toFixed(2);
  };

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-3xl font-bold">📊 A/B Test Results</h2>
        <button
          onClick={() => navigate('/ab-testing')}
          className="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700"
        >
          ← Back to Dashboard
        </button>
      </div>

      {/* Test Info */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h3 className="text-xl font-semibold mb-4">{results.test_name}</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <p className="text-gray-600">Status</p>
            <p className="font-bold">
              <span className={`px-2 py-1 rounded text-sm ${results.status === 'running' ? 'bg-blue-100 text-blue-800' :
                  results.status === 'completed' ? 'bg-green-100 text-green-800' :
                    'bg-gray-100 text-gray-800'
                }`}>
                {results.status}
              </span>
            </p>
          </div>
          <div>
            <p className="text-gray-600">Test Type</p>
            <p className="font-bold">{results.test_type.replace('_', ' ')}</p>
          </div>
          <div>
            <p className="text-gray-600">Sample Size</p>
            <p className="font-bold">{results.sample_size}</p>
          </div>
          <div>
            <p className="text-gray-600">Split</p>
            <p className="font-bold">{results.split_percentage}% / {100 - results.split_percentage}%</p>
          </div>
        </div>

        {results.progress && (
          <div className="mt-4 pt-4 border-t border-gray-200">
            <h4 className="font-semibold text-sm text-gray-700 mb-2">Progress</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-gray-600">Sent (A)</p>
                <p className="font-bold">{results.progress.sent_a || 0} / {results.progress.total_a || 0}</p>
              </div>
              <div>
                <p className="text-gray-600">Sent (B)</p>
                <p className="font-bold">{results.progress.sent_b || 0} / {results.progress.total_b || 0}</p>
              </div>
              <div>
                <p className="text-gray-600">Failed (A)</p>
                <p className="font-bold text-red-600">{results.progress.failed_a || 0}</p>
              </div>
              <div>
                <p className="text-gray-600">Failed (B)</p>
                <p className="font-bold text-red-600">{results.progress.failed_b || 0}</p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Winner Announcement */}
      {results.winner.winner !== "TIE" && (
        <div className="bg-green-50 border-2 border-green-300 rounded-lg p-6 mb-6">
          <p className="text-2xl font-bold text-green-800">
            🏆 Variant {results.winner.winner} is winning by {results.winner.improvement.toFixed(2)}%
          </p>
        </div>
      )}

      {results.winner.winner === "TIE" && (
        <div className="bg-yellow-50 border-2 border-yellow-300 rounded-lg p-6 mb-6">
          <p className="text-xl font-bold text-yellow-800">
            🤝 Both variants are performing equally
          </p>
        </div>
      )}

      {/* Results Table */}
      <div className="bg-white shadow rounded-lg overflow-hidden mb-6">
        <div className="p-4 border-b bg-gray-50">
          <h3 className="text-lg font-semibold">Performance Comparison</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-100">
              <tr>
                <th className="px-6 py-3 text-left">Variant</th>
                <th className="px-6 py-3 text-right">Sent</th>
                <th className="px-6 py-3 text-right">Opened</th>
                <th className="px-6 py-3 text-right">Clicked</th>
                <th className="px-6 py-3 text-right">Open Rate</th>
                <th className="px-6 py-3 text-right">Click Rate</th>
                <th className="px-6 py-3 text-right">CTR</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t hover:bg-gray-50">
                <td className="px-6 py-4 font-semibold">Variant A</td>
                <td className="px-6 py-4 text-right">{results.results.variant_a.sent}</td>
                <td className="px-6 py-4 text-right">{results.results.variant_a.opened}</td>
                <td className="px-6 py-4 text-right">{results.results.variant_a.clicked}</td>
                <td className="px-6 py-4 text-right">{results.results.variant_a.open_rate.toFixed(2)}%</td>
                <td className="px-6 py-4 text-right">{results.results.variant_a.click_rate.toFixed(2)}%</td>
                <td className="px-6 py-4 text-right">{results.results.variant_a.ctr.toFixed(2)}%</td>
              </tr>
              <tr className="border-t bg-blue-50">
                <td className="px-6 py-4 font-semibold">Variant B</td>
                <td className="px-6 py-4 text-right">{results.results.variant_b.sent}</td>
                <td className="px-6 py-4 text-right">{results.results.variant_b.opened}</td>
                <td className="px-6 py-4 text-right">{results.results.variant_b.clicked}</td>
                <td className="px-6 py-4 text-right">{results.results.variant_b.open_rate.toFixed(2)}%</td>
                <td className="px-6 py-4 text-right">{results.results.variant_b.click_rate.toFixed(2)}%</td>
                <td className="px-6 py-4 text-right">{results.results.variant_b.ctr.toFixed(2)}%</td>
              </tr>
              <tr className="border-t bg-gray-100 font-semibold">
                <td className="px-6 py-4">Difference</td>
                <td className="px-6 py-4 text-right">
                  {results.results.variant_b.sent - results.results.variant_a.sent}
                </td>
                <td className="px-6 py-4 text-right">
                  {results.results.variant_b.opened - results.results.variant_a.opened}
                </td>
                <td className="px-6 py-4 text-right">
                  {results.results.variant_b.clicked - results.results.variant_a.clicked}
                </td>
                <td className="px-6 py-4 text-right">
                  <span className={
                    results.results.variant_b.open_rate > results.results.variant_a.open_rate
                      ? 'text-green-600'
                      : results.results.variant_b.open_rate < results.results.variant_a.open_rate
                        ? 'text-red-600'
                        : 'text-gray-600'
                  }>
                    {calculatePercentageDiff(
                      results.results.variant_b.open_rate,
                      results.results.variant_a.open_rate
                    )}%
                  </span>
                </td>
                <td className="px-6 py-4 text-right">
                  <span className={
                    results.results.variant_b.click_rate > results.results.variant_a.click_rate
                      ? 'text-green-600'
                      : results.results.variant_b.click_rate < results.results.variant_a.click_rate
                        ? 'text-red-600'
                        : 'text-gray-600'
                  }>
                    {calculatePercentageDiff(
                      results.results.variant_b.click_rate,
                      results.results.variant_a.click_rate
                    )}%
                  </span>
                </td>
                <td className="px-6 py-4 text-right">
                  <span className={
                    results.results.variant_b.ctr > results.results.variant_a.ctr
                      ? 'text-green-600'
                      : results.results.variant_b.ctr < results.results.variant_a.ctr
                        ? 'text-red-600'
                        : 'text-gray-600'
                  }>
                    {calculatePercentageDiff(
                      results.results.variant_b.ctr,
                      results.results.variant_a.ctr
                    )}%
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Statistical Significance */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">📈 Statistical Significance</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <p className="text-sm text-gray-600">Confidence Level</p>
            <p className="text-2xl font-bold">
              <span className={`px-3 py-1 rounded ${results.statistical_significance.confidence_level === 'high'
                  ? 'bg-green-100 text-green-800'
                  : results.statistical_significance.confidence_level === 'medium'
                    ? 'bg-yellow-100 text-yellow-800'
                    : 'bg-red-100 text-red-800'
                }`}>
                {results.statistical_significance.confidence_level.toUpperCase()}
              </span>
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Total Samples</p>
            <p className="text-2xl font-bold">{results.statistical_significance.total_samples}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Statistically Significant</p>
            <p className="text-2xl font-bold">
              {results.statistical_significance.is_significant ? (
                <span className="text-green-600">✓ Yes</span>
              ) : (
                <span className="text-red-600">✗ No</span>
              )}
            </p>
          </div>
        </div>

        {!results.statistical_significance.is_significant && (
          <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded">
            <p className="text-sm text-yellow-800">
              ⚠️ Sample size is too small for reliable conclusions. Consider running the test longer or increasing the sample size.
            </p>
          </div>
        )}
      </div>

      {/* Visual Chart */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">📊 Visual Comparison</h3>

        <div className="space-y-6">
          {/* Open Rate Comparison */}
          <div>
            <div className="flex justify-between mb-2">
              <span className="text-sm font-medium">Open Rate</span>
              <span className="text-sm text-gray-600">
                A: {results.results.variant_a.open_rate.toFixed(2)}% |
                B: {results.results.variant_b.open_rate.toFixed(2)}%
              </span>
            </div>
            <div className="flex gap-2">
              <div className="flex-1">
                <div className="bg-blue-200 rounded h-8 relative overflow-hidden">
                  <div
                    className="bg-blue-600 h-full rounded transition-all duration-500"
                    style={{ width: `${Math.min(results.results.variant_a.open_rate, 100)}%` }}
                  >
                    <span className="absolute inset-0 flex items-center justify-center text-white text-xs font-bold">
                      Variant A
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex-1">
                <div className="bg-orange-200 rounded h-8 relative overflow-hidden">
                  <div
                    className="bg-orange-600 h-full rounded transition-all duration-500"
                    style={{ width: `${Math.min(results.results.variant_b.open_rate, 100)}%` }}
                  >
                    <span className="absolute inset-0 flex items-center justify-center text-white text-xs font-bold">
                      Variant B
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Click Rate Comparison */}
          <div>
            <div className="flex justify-between mb-2">
              <span className="text-sm font-medium">Click Rate</span>
              <span className="text-sm text-gray-600">
                A: {results.results.variant_a.click_rate.toFixed(2)}% |
                B: {results.results.variant_b.click_rate.toFixed(2)}%
              </span>
            </div>
            <div className="flex gap-2">
              <div className="flex-1">
                <div className="bg-blue-200 rounded h-8 relative overflow-hidden">
                  <div
                    className="bg-blue-600 h-full rounded transition-all duration-500"
                    style={{ width: `${Math.min(results.results.variant_a.click_rate, 100)}%` }}
                  >
                    <span className="absolute inset-0 flex items-center justify-center text-white text-xs font-bold">
                      Variant A
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex-1">
                <div className="bg-orange-200 rounded h-8 relative overflow-hidden">
                  <div
                    className="bg-orange-600 h-full rounded transition-all duration-500"
                    style={{ width: `${Math.min(results.results.variant_b.click_rate, 100)}%` }}
                  >
                    <span className="absolute inset-0 flex items-center justify-center text-white text-xs font-bold">
                      Variant B
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* CTR Comparison */}
          <div>
            <div className="flex justify-between mb-2">
              <span className="text-sm font-medium">Click-Through Rate (CTR)</span>
              <span className="text-sm text-gray-600">
                A: {results.results.variant_a.ctr.toFixed(2)}% |
                B: {results.results.variant_b.ctr.toFixed(2)}%
              </span>
            </div>
            <div className="flex gap-2">
              <div className="flex-1">
                <div className="bg-blue-200 rounded h-8 relative overflow-hidden">
                  <div
                    className="bg-blue-600 h-full rounded transition-all duration-500"
                    style={{ width: `${Math.min(results.results.variant_a.ctr, 100)}%` }}
                  >
                    <span className="absolute inset-0 flex items-center justify-center text-white text-xs font-bold">
                      Variant A
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex-1">
                <div className="bg-orange-200 rounded h-8 relative overflow-hidden">
                  <div
                    className="bg-orange-600 h-full rounded transition-all duration-500"
                    style={{ width: `${Math.min(results.results.variant_b.ctr, 100)}%` }}
                  >
                    <span className="absolute inset-0 flex items-center justify-center text-white text-xs font-bold">
                      Variant B
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Timestamps */}
      {(results.start_date || results.end_date) && (
        <div className="mt-6 bg-gray-50 rounded-lg p-4 text-sm text-gray-600">
          {results.start_date && (
            <p>Started: {new Date(results.start_date).toLocaleString()}</p>
          )}
          {results.end_date && (
            <p>Ended: {new Date(results.end_date).toLocaleString()}</p>
          )}
        </div>
      )}
    </div>
  );
};

export default ABTestResults;