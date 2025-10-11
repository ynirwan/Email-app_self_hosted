import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import API from '../api';

export default function Register() {
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const navigate = useNavigate();

  const handleChange = e => setForm({ ...form, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const res = await API.post('/auth/register', form);
      localStorage.setItem('token', res.data.token);
      navigate('/');
    } catch (err) {
      alert(err.response?.data?.detail || 'Registration failed');
    }
  };

  return (
    <div className="max-w-md mx-auto mt-10">
      <h2 className="text-xl font-bold mb-4">Register</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
	 <input
  className="border p-2 w-full"
  name="name"
  value={form.name}
  onChange={handleChange}
  placeholder="Name"
  required
/>
<input
  className="border p-2 w-full"
  name="email"
  type="email"
  value={form.email}
  onChange={handleChange}
  placeholder="Email"
  required
/>
<input
  className="border p-2 w-full"
  name="password"
  type="password"
  value={form.password}
  onChange={handleChange}
  placeholder="Password"
  required
/>
 
        <button className="bg-blue-600 text-white px-4 py-2 rounded">Register</button>
      </form>
    </div>
  );
}

