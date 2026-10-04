import React, { useEffect, useState } from 'react';
import { api, DemoAccount, ScoreResult } from '../api/client';
import { useI18n } from '../locales/i18n';
import { formatBDT, formatSecondsCountdown, toBengaliDigits } from '../utils/format';
import {
  Send,
  AlertTriangle,
  ShieldCheck,
  Clock,
  ShieldAlert,
  CheckCircle2,
  ArrowRight,
  PhoneCall,
  UserCheck,
  UserPlus,
} from 'lucide-react';
import { AttackDemo } from '../components/AttackDemo';

export const CustomerDemo: React.FC = () => {
  const { lang, t } = useI18n();
  const [accounts, setAccounts] = useState<{ senders: DemoAccount[]; recipients: DemoAccount[] }>({
    senders: [],
    recipients: [],
  });
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [accountError, setAccountError] = useState<string | null>(null);

  const [senderWallet, setSenderWallet] = useState<string>('');
  const [recipientWallet, setRecipientWallet] = useState<string>('');
  const [isCustomRecipient, setIsCustomRecipient] = useState(false);
  const [customRecipient, setCustomRecipient] = useState('');
  const [amount, setAmount] = useState<number>(25000);
  const [reference, setReference] = useState<string>('');

  const [evaluating, setEvaluating] = useState(false);
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [scoreError, setScoreError] = useState<string | null>(null);
  const [feedbackSent, setFeedbackSent] = useState(false);

  // Cooling-off timer for verify action
  const [coolingSeconds, setCoolingSeconds] = useState(60);
  const [trustedContactApproved, setTrustedContactApproved] = useState(false);

  useEffect(() => {
    let mounted = true;
    api.getDemoAccounts()
      .then((data) => {
        if (!mounted) return;
        setAccounts(data);
        if (data.senders.length > 0) setSenderWallet(data.senders[0].wallet_id);
        if (data.recipients.length > 0) setRecipientWallet(data.recipients[0].wallet_id);
      })
      .catch((err) => {
        if (!mounted) return;
        setAccountError(err.message || 'Failed to load demo accounts');
      })
      .finally(() => {
        if (mounted) setLoadingAccounts(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  // Tick down cooling-off timer when in verify action
  useEffect(() => {
    if (result?.action !== 'verify' || coolingSeconds <= 0) return;
    const interval = setInterval(() => {
      setCoolingSeconds((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [result?.action, coolingSeconds]);

  const selectedSender = accounts.senders.find((s) => s.wallet_id === senderWallet);
  const selectedRecipient = isCustomRecipient
    ? null
    : accounts.recipients.find((r) => r.wallet_id === recipientWallet);

  const activeRecipientId = isCustomRecipient ? customRecipient.trim() : recipientWallet;

  const handleScore = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!senderWallet || !activeRecipientId || amount <= 0) return;

    setEvaluating(true);
    setScoreError(null);
    setFeedbackSent(false);
    setCoolingSeconds(60);
    setTrustedContactApproved(false);

    try {
      const res = await api.scoreTransaction({
        txn_id: `TXN-${Date.now().toString().slice(-6)}`,
        type: 'send_money',
        sender_wallet_id: senderWallet,
        recipient_wallet_id: activeRecipientId,
        amount_bdt: Number(amount),
        channel: 'app',
        device_id: 'D-DEMO-001',
        balance_before: selectedSender ? selectedSender.balance_bdt : 50000,
      });
      setResult(res);
    } catch (err: any) {
      setScoreError(err.message || 'Evaluation error occurred');
    } finally {
      setEvaluating(false);
    }
  };

  const handleFeedback = async (label: 'this_was_me' | 'not_me') => {
    if (!result) return;
    try {
      await api.recordFeedback({
        decision_id: result.txn_id,
        source: 'customer',
        label: label,
      });
      setFeedbackSent(true);
    } catch {
      // In mock/test environments
      setFeedbackSent(true);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      {/* Page Header */}
      <div className="mb-8">
        <h1 className="text-2xl lg:text-3xl font-bold tracking-tight text-white font-bengali">
          {t('customer.title')}
        </h1>
        <p className="text-sm text-slate-400 mt-1 font-bengali">
          {t('customer.subtitle')}
        </p>
      </div>

      {/* Live Attack Simulation & Replay */}
      <AttackDemo
        onAttackCompleted={(alertId) => {
          if (alertId) {
            setResult({
              txn_id: 'TXN-ATK-DEMO',
              risk_score: 1.0,
              action: 'hold',
              reason_codes: [
                { code: 'RECIPIENT_FAN_IN_BURST', weight: 0.55 },
                { code: 'AMOUNT_UNUSUAL_FOR_SENDER', weight: 0.35 },
                { code: 'RING_LINK', weight: 0.10 },
              ],
              customer_message: {
                bn: 'অল্প সময়ে অনেকে প্রথমবার এই নম্বরে টাকা পাঠিয়েছেন। এই পরিমাণ আপনার সাধারণ লেনদেনের তুলনায় অনেক বেশি। পাঠানোর আগে আপনার জানা নম্বরে সরাসরি ফোন করে নিশ্চিত হয়ে নিন।',
                en: 'Many people sent money to this number in a short time. This amount is much larger than you usually send. Before sending, call the person on a number you already have.',
              },
              alert_id: alertId,
              model_version: 'm-1.0.0-full',
              policy_version: '0.1',
              latency_ms: 18.5,
            });
          }
        }}
        onResetCompleted={() => {
          setResult(null);
          setScoreError(null);
        }}
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Form: Send Money */}
        <div className="lg:col-span-6 bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-sm">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2 font-bengali">
            <Send className="w-5 h-5 text-teal-400" />
            {t('customer.submit_button')}
          </h2>

          {loadingAccounts ? (
            <div className="py-12 text-center text-slate-400 animate-pulse font-bengali">
              লোড হচ্ছে...
            </div>
          ) : accountError ? (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
              {accountError}
            </div>
          ) : (
            <form onSubmit={handleScore} className="space-y-4">
              {/* Sender Select */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5 font-bengali">
                  {t('customer.sender_label')}
                </label>
                <select
                  value={senderWallet}
                  onChange={(e) => setSenderWallet(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                >
                  {accounts.senders.map((s) => (
                    <option key={s.wallet_id} value={s.wallet_id}>
                      {s.name} ({s.wallet_id}) — {formatBDT(s.balance_bdt, lang)}
                    </option>
                  ))}
                </select>
                {selectedSender && (
                  <p className="text-[11px] text-slate-400 mt-1">{selectedSender.description}</p>
                )}
              </div>

              {/* Recipient Select / Custom Option */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider font-bengali">
                    {t('customer.recipient_label')}
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      setIsCustomRecipient(!isCustomRecipient);
                      if (!isCustomRecipient && !customRecipient) {
                        setCustomRecipient('01899123456');
                      }
                    }}
                    className="text-[11px] text-teal-400 hover:text-teal-300 flex items-center gap-1 font-bengali"
                  >
                    <UserPlus className="w-3 h-3" />
                    <span>{isCustomRecipient ? 'তালিকা থেকে নির্বাচন করুন' : 'নতুন নম্বর লিখুন'}</span>
                  </button>
                </div>

                {!isCustomRecipient ? (
                  <select
                    value={recipientWallet}
                    onChange={(e) => setRecipientWallet(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  >
                    {accounts.recipients.map((r) => (
                      <option key={r.wallet_id} value={r.wallet_id}>
                        {r.name} ({r.wallet_id})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={customRecipient}
                    onChange={(e) => setCustomRecipient(e.target.value)}
                    placeholder="e.g. 01899123456 or W-NEW-MULE"
                    className="w-full bg-slate-950 border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 font-mono"
                  />
                )}

                {selectedRecipient && !isCustomRecipient && (
                  <p className="text-[11px] text-amber-400/90 mt-1">{selectedRecipient.description}</p>
                )}
                {isCustomRecipient && (
                  <p className="text-[11px] text-teal-400 mt-1 font-bengali">
                    নতুন অজানা প্রাপক নম্বর (First-time / novel recipient)
                  </p>
                )}
              </div>

              {/* Amount Input */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5 font-bengali">
                  {t('customer.amount_label')}
                </label>
                <div className="relative">
                  <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 font-semibold">
                    ৳
                  </span>
                  <input
                    type="number"
                    min="10"
                    max="100000"
                    value={amount}
                    onChange={(e) => setAmount(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-700/80 rounded-xl pl-8 pr-4 py-2.5 text-sm text-white focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 font-mono"
                    placeholder="25000"
                  />
                </div>
                <div className="flex flex-wrap gap-2 mt-2">
                  {[500, 5000, 15000, 25000, 35000].map((preset) => (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => setAmount(preset)}
                      className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
                        amount === preset
                          ? 'bg-teal-500/20 border-teal-500 text-teal-300 font-medium'
                          : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white'
                      }`}
                    >
                      {formatBDT(preset, lang)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Reference (Free-text, treated as untrusted) */}
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5 font-bengali">
                  রেফারেন্স (ঐচ্ছিক / Untrusted Note)
                </label>
                <input
                  type="text"
                  maxLength={140}
                  value={reference}
                  onChange={(e) => setReference(e.target.value)}
                  placeholder="রেফারেন্স লিখুন (যেমন: পারিবারিক জরুরি খরচ)"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-teal-500"
                />
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={evaluating || !activeRecipientId}
                className="w-full mt-4 flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-gradient-to-r from-teal-600 to-emerald-600 hover:from-teal-500 hover:to-emerald-500 text-white font-medium shadow-lg shadow-teal-700/25 transition-all disabled:opacity-50 font-bengali"
              >
                {evaluating ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>{t('customer.evaluating')}</span>
                  </>
                ) : (
                  <>
                    <span>{t('customer.submit_button')}</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </form>
          )}
        </div>

        {/* Right Card: Real-Time Interception Output */}
        <div className="lg:col-span-6">
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-sm h-full flex flex-col justify-between">
            <div>
              <h2 className="text-lg font-semibold text-white mb-4 flex items-center justify-between font-bengali">
                <span>{t('customer.result_title')}</span>
                {result && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-teal-400 border border-slate-700 font-mono font-bold">
                    {result.latency_ms.toFixed(1)} ms
                  </span>
                )}
              </h2>

              {scoreError && (
                <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
                  {scoreError}
                </div>
              )}

              {!result && !scoreError && (
                <div className="py-20 text-center text-slate-400 flex flex-col items-center justify-center font-bengali">
                  <ShieldCheck className="w-12 h-12 text-slate-600 mb-3" />
                  <p className="text-sm max-w-xs">{t('customer.empty_state')}</p>
                </div>
              )}

              {result && (
                <div className="space-y-5 animate-in fade-in duration-200">
                  {/* Action Banner */}
                  <div
                    className={`p-4 rounded-xl border flex items-start gap-3.5 ${
                      result.action === 'allow'
                        ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                        : result.action === 'warn'
                        ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                        : result.action === 'verify'
                        ? 'bg-sky-500/10 border-sky-500/30 text-sky-300'
                        : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                    }`}
                  >
                    {result.action === 'allow' && <CheckCircle2 className="w-6 h-6 flex-shrink-0 text-emerald-400" />}
                    {result.action === 'warn' && <AlertTriangle className="w-6 h-6 flex-shrink-0 text-amber-400" />}
                    {result.action === 'verify' && <Clock className="w-6 h-6 flex-shrink-0 text-sky-400" />}
                    {result.action === 'hold' && <ShieldAlert className="w-6 h-6 flex-shrink-0 text-rose-400" />}

                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-base uppercase font-bengali">
                          {result.action === 'allow'
                            ? t('customer.action_allow')
                            : result.action === 'warn'
                            ? t('customer.action_warn')
                            : result.action === 'verify'
                            ? t('customer.action_verify')
                            : t('customer.action_hold')}
                        </span>
                        <span className="text-xs px-2 py-0.5 rounded bg-slate-900/60 font-mono font-bold">
                          p={lang === 'bn' ? toBengaliDigits((result.risk_score * 100).toFixed(0)) : (result.risk_score * 100).toFixed(0)}%
                        </span>
                      </div>
                      <p className="text-sm mt-1 leading-relaxed font-bengali">
                        {lang === 'bn' ? result.customer_message.bn : result.customer_message.en}
                      </p>
                    </div>
                  </div>

                  {/* Reasons Chips */}
                  {result.reason_codes.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2 font-bengali">
                        {t('customer.reasons_title')}
                      </h3>
                      <div className="space-y-2">
                        {result.reason_codes.map((rc) => (
                          <div
                            key={rc.code}
                            className="flex items-center justify-between text-xs px-3 py-2 rounded-lg bg-slate-950 border border-slate-800"
                          >
                            <span className="font-mono text-teal-400 font-medium">{rc.code}</span>
                            <span className="text-slate-400 font-mono">
                              {lang === 'bn' ? toBengaliDigits((rc.weight * 100).toFixed(0)) : (rc.weight * 100).toFixed(0)}% weight
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Warn Intervention Actions */}
                  {result.action === 'warn' && (
                    <div className="space-y-3 pt-1">
                      <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300 flex items-center gap-2 font-bengali">
                        <PhoneCall className="w-4 h-4 flex-shrink-0 text-amber-400" />
                        <span>
                          {lang === 'bn'
                            ? 'পাঠানোর আগে আপনার জানা নম্বরে সরাসরি ফোন করে নিশ্চিত হয়ে নিন।'
                            : 'Before sending, call the person on a number you already have.'}
                        </span>
                      </div>
                      {!feedbackSent ? (
                        <div className="flex gap-3">
                          <button
                            onClick={() => handleFeedback('not_me')}
                            className="flex-1 py-2 px-3 rounded-lg border border-slate-700 bg-slate-800 text-xs font-medium text-slate-300 hover:bg-slate-700 font-bengali"
                          >
                            {t('customer.warning_cancel')}
                          </button>
                          <button
                            onClick={() => handleFeedback('this_was_me')}
                            className="flex-1 py-2 px-3 rounded-lg bg-amber-600 hover:bg-amber-500 text-xs font-medium text-white font-bengali shadow"
                          >
                            {t('customer.warning_continue')}
                          </button>
                        </div>
                      ) : (
                        <p className="text-emerald-400 text-center text-xs font-bengali py-1">
                          ✓ প্রতিক্রিয়া সংরক্ষিত হয়েছে (Customer continuation recorded)
                        </p>
                      )}
                    </div>
                  )}

                  {/* Verify Intervention: Cooling-Off & Trusted-Contact Simulation */}
                  {result.action === 'verify' && (
                    <div className="p-4 rounded-xl bg-slate-950 border border-sky-500/30 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Clock className="w-4 h-4 text-sky-400" />
                          <span className="text-xs font-bold text-white font-bengali">
                            নিরাপত্তা বিরতি (Cooling-off Countdown)
                          </span>
                        </div>
                        <span className="text-sm font-mono font-bold text-sky-300">
                          {formatSecondsCountdown(coolingSeconds, lang)}
                        </span>
                      </div>

                      <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-sky-500 h-1.5 transition-all duration-1000"
                          style={{ width: `${(coolingSeconds / 60) * 100}%` }}
                        />
                      </div>

                      <div className="pt-2 border-t border-slate-800">
                        <div className="flex items-center justify-between text-xs mb-2">
                          <span className="text-slate-400 font-bengali">বিশ্বস্ত পরিচিত ব্যক্তির যাচাই:</span>
                          <span className="text-slate-200 font-medium">সালমা বেগম (+88017***)</span>
                        </div>

                        {!trustedContactApproved ? (
                          <button
                            type="button"
                            onClick={() => setTrustedContactApproved(true)}
                            className="w-full py-2 px-3 rounded-lg bg-sky-600 hover:bg-sky-500 text-xs font-medium text-white flex items-center justify-center gap-2 font-bengali shadow"
                          >
                            <UserCheck className="w-4 h-4" />
                            <span>পরিচিত ব্যক্তির অনুমোদন নিশ্চিত করুন (Simulate Contact Confirmation)</span>
                          </button>
                        ) : (
                          <div className="p-2 rounded-lg bg-emerald-500/20 text-emerald-300 text-xs font-bengali text-center font-bold">
                            ✓ বিশ্বস্ত ব্যক্তির অনুমোদন সম্পন্ন হয়েছে
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Hold Intervention: Golden Window & Feedback */}
                  {result.action === 'hold' && (
                    <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-300 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <span className="text-slate-400 font-bengali">গোল্ডেন উইন্ডো লক্ষ্যমাত্রা:</span>
                        <span className="font-bold text-amber-300">
                          {lang === 'bn' ? '৩০ মিনিট' : '30 minutes'}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-slate-400 font-bengali">অ্যালার্ট রেফারেন্স:</span>
                        <span className="font-mono text-teal-400 font-bold">{result.alert_id || 'A-PENDING'}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-slate-400 font-bengali">পর্যালোচনা অবস্থা:</span>
                        <span className="text-rose-400 font-semibold uppercase">Open in Analyst Queue</span>
                      </div>

                      {!feedbackSent ? (
                        <button
                          onClick={() => handleFeedback('this_was_me')}
                          className="w-full mt-2 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 border border-slate-700 font-bengali transition-colors"
                        >
                          আমি নিজেই এই লেনদেনটি করেছি (This was me)
                        </button>
                      ) : (
                        <p className="text-emerald-400 text-center text-xs font-bengali mt-1">
                          ✓ আপনার প্রতিক্রিয়া অ্যানালিস্ট কিউ-তে পাঠানো হয়েছে
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="pt-6 border-t border-slate-800/80 mt-6 text-[11px] text-slate-400 flex items-center justify-between font-mono">
              <span>Model: {result?.model_version || 'm-1.0.0-full'}</span>
              <span>Policy: v{result?.policy_version || '0.1'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
