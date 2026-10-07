import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { I18nProvider } from './locales/i18n';
import { AuthProvider } from './context/AuthContext';
import { Navbar } from './components/Navbar';
import { CustomerDemo } from './pages/CustomerDemo';
import { AnalystConsole } from './pages/AnalystConsole';
import { Metrics } from './pages/Metrics';
import { Login } from './pages/Login';

export const App: React.FC = () => {
  return (
    <I18nProvider>
      <AuthProvider>
        <BrowserRouter>
          <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
            <Navbar />
            <main className="flex-1">
              <Routes>
                <Route path="/" element={<CustomerDemo />} />
                <Route path="/analyst" element={<AnalystConsole />} />
                <Route path="/metrics" element={<Metrics />} />
                <Route path="/login" element={<Login />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </main>
          </div>
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  );
};

export default App;
