import { useState } from 'react';
import API, { setTokens } from '../api';

export default function Register() {
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleChange = (e) =>
    setForm({ ...form, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading) return;
    setError(null);
    setLoading(true);

    try {
      const res = await API.post('/auth/register', form);
      setTokens({
        access: res.data.access_token || res.data.token,
        refresh: res.data.refresh_token,
      });
      // Hard reload so App.jsx re-evaluates `isLoggedIn`. Using react-router's
      // navigate('/') here would land on the protected route shell BEFORE the
      // route gate notices the new token, bouncing the user back to /login.
      window.location.assign('/');
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          err.response?.data?.message ||
          'Registration failed',
      );
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto mt-10">
      <h2 className="text-xl font-bold mb-4">Register</h2>

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <input
          className="border p-2 w-full"
          name="name"
          value={form.name}
          onChange={handleChange}
          placeholder="Name"
          required
          disabled={loading}
          autoComplete="name"
        />
        <input
          className="border p-2 w-full"
          name="email"
          type="email"
          value={form.email}
          onChange={handleChange}
          placeholder="Email"
          required
          disabled={loading}
          autoComplete="email"
        />
        <input
          className="border p-2 w-full"
          name="password"
          type="password"
          value={form.password}
          onChange={handleChange}
          placeholder="Password (min 8 characters)"
          required
          minLength={8}
          disabled={loading}
          autoComplete="new-password"
        />
        <button
          type="submit"
          disabled={loading}
          className={`px-4 py-2 rounded text-white ${
            loading ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'
          }`}
        >
          {loading ? 'Creating account…' : 'Register'}
        </button>
      </form>
    </div>
  );
}
