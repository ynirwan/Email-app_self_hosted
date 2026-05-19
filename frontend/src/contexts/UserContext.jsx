import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import API, { getAccessToken } from '../api';

const UserContext = createContext(null);

export function UserProvider({ children }) {
  const [user, setUser] = useState(null);
  const [userLoading, setUserLoading] = useState(true);

  const fetchUser = useCallback(async () => {
    if (!getAccessToken()) {
      setUserLoading(false);
      return;
    }
    try {
      const res = await API.get('/auth/me');
      setUser(res.data);
    } catch (err) {
      // api.js interceptor handles 401 (refresh-then-retry, hard logout on
      // refresh failure). Anything bubbling up here is a non-auth failure
      // (network, server) — leave user state null and let downstream code
      // recover. We never want this hook to forcibly navigate the user.
    } finally {
      setUserLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  return (
    <UserContext.Provider value={{ user, userLoading, refetchUser: fetchUser }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  return useContext(UserContext);
}
