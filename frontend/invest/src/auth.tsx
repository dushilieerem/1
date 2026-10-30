import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getToken, loginRequest, setToken, ssoRequest } from "./api";

type AuthUser = {
  id: number;
  username: string;
  display_name: string;
  role: string;
  status: string;
};

type AuthCtx = {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (payload: { username: string; password: string; email?: string; display_name?: string }) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const data = await api<{ user: AuthUser }>("/api/auth/me");
      setUser(data.user);
    } catch {
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const boot = async () => {
      const hash = window.location.hash || "";
      const match = hash.match(/(?:^#|&)svq_token=([^&]+)/);
      if (match && !getToken()) {
        try {
          await ssoRequest(decodeURIComponent(match[1]));
        } catch {
          /* fall back to normal login */
        } finally {
          history.replaceState(null, "", location.pathname + location.search);
        }
      }
      await refresh();
    };
    void boot();
    const onExpired = () => {
      setToken(null);
      setUser(null);
      setLoading(false);
    };
    window.addEventListener("svq:auth-expired", onExpired);
    return () => window.removeEventListener("svq:auth-expired", onExpired);
  }, []);

  const login = async (username: string, password: string) => {
    const data = await loginRequest(username, password);
    setUser(data.user);
  };

  const register = async (payload: { username: string; password: string; email?: string; display_name?: string }) => {
    const data = await api<{ token: string; user: AuthUser }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setToken(data.token);
    setUser(data.user);
  };

  const logout = () => {
    setToken(null);
    setUser(null);
  };

  const value = useMemo(() => ({ user, loading, login, register, logout, refresh }), [user, loading]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
