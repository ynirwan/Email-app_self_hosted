// frontend/src/api.js
import axios from "axios";

const API = axios.create({
  baseURL:
    "https://1e3e51b5-d74b-43fc-9d8d-5d25ea6cb6c7-00-3fzv7fuo5ld08.picard.replit.dev:8000/api",
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
