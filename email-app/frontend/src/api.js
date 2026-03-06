// frontend/src/api.js
import axios from "axios";

const getBaseURL = () => {
  if (window.location.hostname.includes('replit.dev')) {
    const protocol = window.location.protocol;
    const host = window.location.host;
    // Replace the port or add it if missing. Replit dev domains usually handle routing.
    // If the backend is on 8000 and frontend on 5000, we need to point to the 8000 port host.
    return `${protocol}//${host.replace('.pike.replit.dev', '.pike.replit.dev')}/api`.replace(':5000', ':8000');
  }
  return "http://localhost:8000/api";
};

const API = axios.create({
  baseURL: getBaseURL(),
});

// ✅ SIMPLIFIED - REMOVED all slash manipulation logic
API.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
      console.log("🔑 Token attached to request:", config.url);
    }
    return config;
  },
  (error) => Promise.reject(error),
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
