import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { I18nProvider } from './locales/i18n';
import { Navbar } from './components/Navbar';
import { CustomerDemo } from './pages/CustomerDemo';
import { AnalystConsole } from './pages/AnalystConsole';
import { Metrics } from './pages/Metrics';

export const App: React.FC = () => {
  return (
    <I18nProvider>
      <BrowserRouter>
        <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
          <Navbar />
          <main className="flex-1">
            <Routes>
              <Route path="/" element={<CustomerDemo />} />
              <Route path="/analyst" element={<AnalystConsole />} />
              <Route path="/metrics" element={<Metrics />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </I18nProvider>
  );
};

export default App;
