import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { Shield, Activity, BarChart3, Globe, Sparkles, AlertTriangle } from 'lucide-react';
import { useI18n } from '../locales/i18n';
import { api } from '../api/client';

export const Navbar: React.FC = () => {
  const { toggleLang, t } = useI18n();
  const [isDegraded, setIsDegraded] = useState(false);

  useEffect(() => {
    let mounted = true;
    api.checkHealth()
      .then((res) => {
        if (mounted && (res.degraded || res.models_loaded === false)) {
          setIsDegraded(true);
        }
      })
      .catch(() => {
        // network / offline
      });
    return () => {
      mounted = false;
    };
  }, []);

  const navItemClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${isActive
      ? 'bg-teal-500/20 text-teal-400 border border-teal-500/30 shadow-sm shadow-teal-500/10'
      : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
    }`;

  return (
    <header className="sticky top-0 z-50 backdrop-blur-md bg-slate-950/80 border-b border-slate-800/80">
      {isDegraded && (
        <div
          data-testid="degraded-banner"
          className="bg-rose-950/90 border-b border-rose-500/40 px-4 py-2 text-center text-xs text-rose-200 flex items-center justify-center gap-2 font-medium shadow-inner"
        >
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
          <span className="font-bengali">{t('degraded_banner')}</span>
        </div>
      )}
      <div className="max-w-7xl mx-auto flex items-center justify-between px-4 lg:px-8 py-3">
        {/* Brand & Logo */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-teal-600 to-emerald-400 flex items-center justify-center shadow-lg shadow-teal-600/30 text-white font-bold">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold tracking-tight text-lg text-white font-bengali">
                  {t('app_title')}
                </span>
                <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  upay
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-bengali hidden sm:block">
                {t('app_subtitle')}
              </p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="hidden md:flex items-center gap-1">
            <NavLink to="/" className={navItemClass}>
              <Shield className="w-4 h-4" />
              <span className="font-bengali">{t('nav_customer')}</span>
            </NavLink>
            <NavLink to="/analyst" className={navItemClass}>
              <Activity className="w-4 h-4" />
              <span className="font-bengali">{t('nav_analyst')}</span>
            </NavLink>
            <NavLink to="/metrics" className={navItemClass}>
              <BarChart3 className="w-4 h-4" />
              <span className="font-bengali">{t('nav_metrics')}</span>
            </NavLink>
          </nav>
        </div>

        {/* Right Action Bar */}
        <div className="flex items-center gap-3">
          {/* Demo Data Badge */}
          <div
            data-testid="demo-data-badge"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/30 shadow-sm shadow-amber-500/10"
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
            <span className="font-bengali">{t('demo_data_badge')}</span>
          </div>

          {/* Language Toggle */}
          <button
            onClick={toggleLang}
            aria-label="Toggle language"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700/60 transition-colors shadow-sm"
          >
            <Globe className="w-3.5 h-3.5 text-teal-400" />
            <span className="font-bengali">{t('language_toggle')}</span>
          </button>
        </div>
      </div>
    </header>
  );
};
