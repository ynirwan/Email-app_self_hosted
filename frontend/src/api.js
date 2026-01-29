// frontend/src/api.js
import axios from "axios";

const API = axios.create({
  baseURL:
    "https://5474f674-6074-4eb8-8818-15946bef35a1-00-1y8lhfj74gqcq.pike.replit.dev:8000/api",
});

// Fix 307 Redirects by ensuring trailing slashes for POST/PUT requests
API.interceptors.request.use(
  (config) => {
    if ((config.method === 'post' || config.method === 'put') && !config.url.endsWith('/')) {
      config.url += '/';
    }
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
      console.log("🔑 Token attached to request:", config.url);
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor to handle 401 errors
API.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.warn("🚫 Unauthorized - clearing token and redirecting to login");
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

export default API;
