import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield, User, Lock, ArrowRight, UserCheck, Award, AlertCircle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useI18n } from '../locales/i18n';

export const Login: React.FC = () => {
  const { login, switchPersona } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();

  const [username, setUsername] = useState('analyst_karim');
  const [password, setPassword] = useState('AnalystPass123!');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
      navigate('/analyst');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickLogin = async (role: 'analyst' | 'senior_analyst' | 'admin') => {
    setError(null);
    setLoading(true);
    try {
      await switchPersona(role);
      navigate('/analyst');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Quick login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center p-4 bg-slate-950">
      <div className="w-full max-w-md bg-slate-900/90 backdrop-blur-xl border border-slate-800 rounded-2xl shadow-2xl p-6 md:p-8">
        {/* Brand */}
        <div className="flex flex-col items-center mb-6">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-teal-500 to-emerald-400 flex items-center justify-center text-slate-950 shadow-lg shadow-teal-500/20 mb-3">
            <Shield className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-xl font-bold text-white font-bengali tracking-tight">
            {t('app_title')} — সুরক্ষিত লগইন
          </h1>
          <p className="text-xs text-slate-400 font-bengali mt-1">
            ব্যক্তিগত লগইন ও ক্রিপ্টোগ্রাফিক অডিট ট্রেইল (Phase 3)
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">ইউজারনেম (Username)</label>
            <div className="relative">
              <User className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                className="w-full pl-9 pr-3 py-2.5 bg-slate-950 border border-slate-700/80 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-teal-500 transition-colors"
                placeholder="analyst_karim"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">পাসওয়ার্ড (Password)</label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full pl-9 pr-3 py-2.5 bg-slate-950 border border-slate-700/80 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-teal-500 transition-colors"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 py-2.5 px-4 bg-gradient-to-r from-teal-500 to-emerald-500 text-slate-950 font-semibold rounded-xl text-sm shadow-md shadow-teal-500/20 hover:from-teal-400 hover:to-emerald-400 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <span>{loading ? 'যাচাই করা হচ্ছে...' : 'লগইন করুন (Sign In)'}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>

        {/* Quick Demo Switchers for Hackathon Judges */}
        <div className="mt-8 pt-6 border-t border-slate-800">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider text-center mb-3">
            বিচারক ও পরীক্ষকদের জন্য ডেমো অ্যাকাউন্টস
          </p>
          <div className="space-y-2">
            <button
              onClick={() => handleQuickLogin('analyst')}
              disabled={loading}
              className="w-full p-2.5 bg-slate-950/60 border border-slate-800 hover:border-teal-500/50 hover:bg-slate-800/40 rounded-xl flex items-center justify-between transition-all group"
            >
              <div className="flex items-center gap-2.5 text-left">
                <div className="w-7 h-7 rounded-lg bg-teal-500/10 border border-teal-500/30 flex items-center justify-center text-teal-400">
                  <UserCheck className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white group-hover:text-teal-300">
                    Karim Chowdhury
                  </div>
                  <div className="text-[10px] text-slate-400">Junior Analyst (Standard Actions)</div>
                </div>
              </div>
              <span className="text-[10px] bg-slate-800 px-2 py-0.5 rounded text-slate-300">Login</span>
            </button>

            <button
              onClick={() => handleQuickLogin('senior_analyst')}
              disabled={loading}
              className="w-full p-2.5 bg-slate-950/60 border border-slate-800 hover:border-amber-500/50 hover:bg-slate-800/40 rounded-xl flex items-center justify-between transition-all group"
            >
              <div className="flex items-center gap-2.5 text-left">
                <div className="w-7 h-7 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
                  <Award className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white group-hover:text-amber-300">
                    Ayesha Siddiqua
                  </div>
                  <div className="text-[10px] text-slate-400">Senior Analyst (Four-Eyes Approval $\ge$ ৳50k)</div>
                </div>
              </div>
              <span className="text-[10px] bg-slate-800 px-2 py-0.5 rounded text-slate-300">Login</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
