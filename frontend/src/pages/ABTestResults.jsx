// components/ABTestResults.jsx
const ABTestResults = ({ testId }) => {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchResults = async () => {
      const response = await fetch(`/api/ab-tests/${testId}/results`);
      const data = await response.json();
      setResults(data);
      setLoading(false);
    };
    
    fetchResults();
    // Refresh every 30 seconds for real-time updates
    const interval = setInterval(fetchResults, 30000);
    return () => clearInterval(interval);
  }, [testId]);

  if (loading) return <div>Loading results...</div>;

  return (
    <div className="ab-test-results">
      <h2>A/B Test Results</h2>
      
      <div className="results-summary">
        {results.winner.winner !== "TIE" && (
          <div className="winner-announcement">
            🏆 Variant {results.winner.winner} is winning by {results.winner.improvement.toFixed(2)}%
          </div>
        )}
      </div>
      
      <div className="results-table">
        <table>
          <thead>
            <tr>
              <th>Variant</th>
              <th>Sent</th>
              <th>Opened</th>
              <th>Clicked</th>
              <th>Open Rate</th>
              <th>Click Rate</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Variant A</td>
              <td>{results.results.variant_a.sent}</td>
              <td>{results.results.variant_a.opened}</td>
              <td>{results.results.variant_a.clicked}</td>
              <td>{results.results.variant_a.open_rate.toFixed(2)}%</td>
              <td>{results.results.variant_a.click_rate.toFixed(2)}%</td>
            </tr>
            <tr>
              <td>Variant B</td>
              <td>{results.results.variant_b.sent}</td>
              <td>{results.results.variant_b.opened}</td>
              <td>{results.results.variant_b.clicked}</td>
              <td>{results.results.variant_b.open_rate.toFixed(2)}%</td>
              <td>{results.results.variant_b.click_rate.toFixed(2)}%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
};

