import React, { useState } from 'react';
import { api, SimulateAttackStep } from '../api/client';
import { useI18n } from '../locales/i18n';
import { formatBDT, toBengaliDigits } from '../utils/format';
import {
  Play,
  RotateCcw,
  Sparkles,
} from 'lucide-react';

interface AttackDemoProps {
  onAttackCompleted?: (finalAlertId?: string) => void;
  onResetCompleted?: () => void;
}

export const AttackDemo: React.FC<AttackDemoProps> = ({
  onAttackCompleted,
  onResetCompleted,
}) => {
  const { lang } = useI18n();
  const [running, setRunning] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [steps, setSteps] = useState<SimulateAttackStep[]>([]);
  const [activeStepIndex, setActiveStepIndex] = useState<number>(-1);
  const [message, setMessage] = useState<string | null>(null);

  const handleRunAttack = async () => {
    setRunning(true);
    setMessage(null);
    setSteps([]);
    setActiveStepIndex(-1);

    try {
      const res = await api.simulateAttack('impersonation_scam_01');
      setSteps(res.steps);

      // Animate steps sequentially for live demo effect
      for (let i = 0; i < res.steps.length; i++) {
        setActiveStepIndex(i);
        // Wait 400ms between steps for visual progression
        await new Promise((r) => setTimeout(r, 400));
      }

      setMessage(res.message);
      const lastStep = res.steps[res.steps.length - 1];
      if (onAttackCompleted) {
        onAttackCompleted(lastStep?.alert_id || undefined);
      }
    } catch (err: any) {
      setMessage(`Attack simulation failed: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const handleReset = async () => {
    setResetting(true);
    setMessage(null);
    try {
      const res = await api.simulateReset();
      setSteps([]);
      setActiveStepIndex(-1);
      setMessage(res.message);
      if (onResetCompleted) {
        onResetCompleted();
      }
    } catch (err: any) {
      setMessage(`Reset failed: ${err.message}`);
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-sm mb-8">
      {/* Header with Title and Synthetic Badge */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800/80">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-white flex items-center gap-2 font-bengali">
              <Sparkles className="w-4 h-4 text-amber-400" />
              <span>লাইভ স্ক্যাম ও অ্যাটাক সিমুলেশন (Live Attack Replay)</span>
            </h2>
            <span
              data-testid="illustrative-scenario-badge"
              className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-amber-500/10 text-amber-300 border border-amber-500/30 uppercase tracking-wider"
            >
              Illustrative scenario (synthetic)
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5 font-bengali">
            {lang === 'bn'
              ? 'একটি নতুন মিউল ওয়ালেটে একাধিক ভুক্তভোগীর অর্থ স্থানান্তরের মাধ্যমে ফ্রড নেটওয়ার্ক রিং সংকেত তৈরি ও গোল্ডেন-মিনিটস ইন্টারসেপশন পর্যবেক্ষণ করুন।'
              : 'Simulate progressive multi-victim fan-in to a fresh mule wallet and observe real-time AI interception.'}
          </p>
        </div>

        {/* Buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleRunAttack}
            disabled={running || resetting}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white text-xs font-semibold shadow-lg shadow-rose-900/20 disabled:opacity-50 transition-all font-bengali"
          >
            {running ? (
              <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5 fill-current" />
            )}
            <span>{lang === 'bn' ? 'অ্যাটাক চালান (Run attack)' : 'Run attack'}</span>
          </button>

          <button
            onClick={handleReset}
            disabled={running || resetting}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium border border-slate-700 disabled:opacity-50 transition-all font-bengali"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${resetting ? 'animate-spin' : ''}`} />
            <span>{lang === 'bn' ? 'রিসেট (Reset demo)' : 'Reset demo'}</span>
          </button>
        </div>
      </div>

      {/* Message Banner */}
      {message && (
        <div className="mt-4 p-3 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-300 font-mono flex items-center justify-between">
          <span>{message}</span>
        </div>
      )}

      {/* Scripted Steps Progression */}
      {steps.length > 0 && (
        <div className="mt-5 space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-400 font-bengali">
            <span>সিনারিও অগ্রগতি (Escalation Pipeline)</span>
            <span className="font-mono text-teal-400">
              Step {lang === 'bn' ? toBengaliDigits(activeStepIndex + 1) : activeStepIndex + 1} of {lang === 'bn' ? toBengaliDigits(steps.length) : steps.length}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-5 gap-2">
            {steps.map((st, idx) => {
              const isPast = idx <= activeStepIndex;
              const isCurrent = idx === activeStepIndex;
              const action = st.action || 'allow';

              return (
                <div
                  key={st.step}
                  className={`p-3 rounded-xl border text-xs transition-all ${isCurrent
                      ? 'ring-2 ring-teal-500/60 bg-slate-950 border-teal-500/60 shadow-lg shadow-teal-500/10'
                      : isPast
                        ? 'bg-slate-950/90 border-slate-800'
                        : 'bg-slate-950/40 border-slate-900 opacity-50'
                    }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-mono font-bold text-slate-400 text-[10px]">
                      STEP {lang === 'bn' ? toBengaliDigits(st.step) : st.step}
                    </span>
                    {st.action && (
                      <span
                        className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase ${action === 'hold'
                            ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                            : action === 'warn'
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                              : action === 'verify'
                                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                                : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          }`}
                      >
                        {action}
                      </span>
                    )}
                  </div>

                  {st.amount_bdt != null && (
                    <div className="font-bold text-white font-mono text-sm mb-1">
                      {formatBDT(st.amount_bdt, lang)}
                    </div>
                  )}

                  <p className="text-[11px] text-slate-300 leading-relaxed font-bengali line-clamp-3">
                    {lang === 'bn' && st.description_bn ? st.description_bn : st.description}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
