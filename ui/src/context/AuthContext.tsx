import React, { createContext, useContext, useState, useEffect } from 'react';
import { api, UserSummary } from '../api/client';

interface AuthContextType {
  user: UserSummary | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password?: string) => Promise<void>;
  logout: () => Promise<void>;
  switchPersona: (role: 'analyst' | 'senior_analyst' | 'admin') => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Try restoring current session
    api.getCurrentUser()
      .then((u) => {
        setUser(u);
      })
      .catch(() => {
        // Fallback default demo login as Karim for seamless demo experience
        api.login('analyst_karim', 'AnalystPass123!')
          .then((res) => setUser(res.user))
          .catch(() => setUser(null));
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = async (username: string, password = 'AnalystPass123!') => {
    setIsLoading(true);
    try {
      const res = await api.login(username, password);
      setUser(res.user);
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    setIsLoading(true);
    try {
      await api.logout();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  const switchPersona = async (role: 'analyst' | 'senior_analyst' | 'admin') => {
    if (role === 'senior_analyst') {
      await login('senior_ayesha', 'SeniorPass123!');
    } else if (role === 'admin') {
      await login('admin_tariq', 'AdminPass123!');
    } else {
      await login('analyst_karim', 'AnalystPass123!');
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
        switchPersona,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
