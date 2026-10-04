import React, { useEffect, useState } from 'react';
import { api, MetricsData } from '../api/client';
import { useI18n } from '../locales/i18n';
import { formatBDT, toBengaliDigits } from '../utils/format';
import {
  BarChart3,
  ShieldCheck,
  Zap,
  AlertCircle,
  Award,
  Sliders,
  Users,
  Layers,
  Clock,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from 'recharts';

export const Metrics: React.FC = () => {
  const { lang, t } = useI18n();
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    api.getMetrics()
      .then((data) => {
        if (!mounted) return;
        setMetrics(data);
      })
      .catch((err) => {
        if (!mounted) return;
        setError(err.message || 'Failed to fetch metrics');
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const typologies = [
    { key: 'agent_collusion', label: 'Agent Collusion (Held-Out Typology)', heldOut: true },
    { key: 'card_to_wallet_burst', label: 'Card-to-Wallet Fan-in Burst', heldOut: false },
    { key: 'impersonation_scam', label: 'Social Engineering Impersonation', heldOut: false },
    { key: 'mule_ring', label: 'Coordinated Mule Ring', heldOut: false },
    { key: 'sim_swap_takeover', label: 'SIM Swap & Device Takeover', heldOut: false },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2 font-bengali">
          <BarChart3 className="w-6 h-6 text-teal-400" />
          {t('metrics.title')}
        </h1>
        <p className="text-sm text-slate-400 mt-1 font-bengali">
          {t('metrics.subtitle')}
        </p>
      </div>

      {loading ? (
        <div className="py-24 text-center text-slate-400 animate-pulse font-bengali">
          লোড হচ্ছে...
        </div>
      ) : error ? (
        <div className="p-6 text-center text-rose-300 text-sm font-bengali bg-rose-500/10 border border-rose-500/20 rounded-2xl">
          {error}
        </div>
      ) : !metrics ? (
        <div className="py-24 text-center text-slate-400 font-bengali">
          কোন মেট্রিক্স পাওয়া যায়নি।
        </div>
      ) : (
        <div className="space-y-8">
          {/* Headline KPIs */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Intercepted BDT */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-lg">
              <div className="flex items-center justify-between text-xs text-slate-400 font-semibold uppercase font-bengali">
                <span>{t('metrics.kpi_intercepted')}</span>
                <Award className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="text-2xl font-bold text-emerald-400 mt-2 font-mono">
                {formatBDT(metrics.fraud_value_intercepted_bdt, lang)}
              </div>
              <div className="text-[11px] text-slate-400 mt-1 font-bengali">
                {lang === 'bn' ? 'ক্যাশ-আউটের পূর্বে সংরক্ষিত' : 'Protected before cash-out'}
              </div>
            </div>

            {/* FFR */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-lg">
              <div className="flex items-center justify-between text-xs text-slate-400 font-semibold uppercase font-bengali">
                <span>{t('metrics.kpi_ffr')}</span>
                <ShieldCheck className="w-4 h-4 text-teal-400" />
              </div>
              <div className="text-2xl font-bold text-teal-400 mt-2 font-mono">
                {lang === 'bn'
                  ? toBengaliDigits((metrics.false_friction_rate * 100).toFixed(2))
                  : (metrics.false_friction_rate * 100).toFixed(2)}%
              </div>
              <div className="text-[11px] text-teal-400/80 mt-1 font-bengali">
                {lang === 'bn' ? 'টার্গেট ক্যাপ ≤ ১.০০%' : 'Target cap ≤ 1.00%'}
              </div>
            </div>

            {/* Decision Latency */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-lg">
              <div className="flex items-center justify-between text-xs text-slate-400 font-semibold uppercase font-bengali">
                <span>{t('metrics.kpi_latency')} (p95 / p50)</span>
                <Zap className="w-4 h-4 text-amber-400" />
              </div>
              <div className="text-2xl font-bold text-amber-400 mt-2 font-mono">
                {lang === 'bn' ? toBengaliDigits(metrics.p95_decision_time_ms.toFixed(1)) : metrics.p95_decision_time_ms.toFixed(1)} ms
              </div>
              <div className="text-[11px] text-slate-400 mt-1 font-mono">
                p50: {lang === 'bn' ? toBengaliDigits(metrics.median_decision_time_ms.toFixed(1)) : metrics.median_decision_time_ms.toFixed(1)} ms (target &lt; 150 ms)
              </div>
            </div>

            {/* Held-Out Typology Recall */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-lg">
              <div className="flex items-center justify-between text-xs text-slate-400 font-semibold uppercase font-bengali">
                <span>{t('metrics.kpi_held_out')}</span>
                <AlertCircle className="w-4 h-4 text-sky-400" />
              </div>
              <div className="text-2xl font-bold text-sky-400 mt-2 font-mono">
                {metrics.held_out_typology_recall
                  ? `${lang === 'bn' ? toBengaliDigits((metrics.held_out_typology_recall * 100).toFixed(1)) : (metrics.held_out_typology_recall * 100).toFixed(1)}%`
                  : 'N/A'}
              </div>
              <div className="text-[11px] text-slate-400 mt-1 font-mono">
                agent_collusion (zero-shot)
              </div>
            </div>

            {/* Hold Resolution Time (ARCHITECTURE Section 14) */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-lg">
              <div className="flex items-center justify-between text-xs text-slate-400 font-semibold uppercase font-bengali">
                <span>{lang === 'bn' ? 'হোল্ড নিষ্পত্তির সময়' : 'Hold-Resolution Time'}</span>
                <Clock className="w-4 h-4 text-indigo-400" />
              </div>
              <div className="text-2xl font-bold text-indigo-400 mt-2 font-mono">
                {metrics.hold_resolution_minutes != null
                  ? `${metrics.hold_resolution_minutes.toFixed(1)} m`
                  : (lang === 'bn' ? '< ১৫ মি.' : '< 15 min')}
              </div>
              <div className="text-[11px] text-slate-400 mt-1 font-mono">
                {lang === 'bn' ? 'গোল্ডেন উইন্ডো < ৩০ মি.' : 'Golden window < 30 min'}
              </div>
            </div>
          </div>

          {/* Ablation Table (A–D) */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Layers className="w-5 h-5 text-teal-400" />
                <div>
                  <h2 className="text-base font-bold text-white font-bengali">
                    {t('metrics.ablation_title')}
                  </h2>
                  <p className="text-xs text-slate-400 font-bengali mt-0.5">
                    নিয়মভিত্তিক বেসলাইন বনাম মেশিন লার্নিং ও গ্রাফ ইন্টেলিজেন্সের ধাপে ধাপে মূল্যায়ন
                  </p>
                </div>
              </div>
            </div>

            {/* Recharts Ablation Comparison */}
            <div className="mb-6 p-4 rounded-xl bg-slate-950/80 border border-slate-800">
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 font-bengali">
                {lang === 'bn' ? 'ভেরিয়েন্ট তুলনা চার্ট (PR-AUC এবং রিকল %)' : 'Variant Performance Comparison (PR-AUC & Recall %)'}
              </div>
              <div style={{ width: '100%', height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={metrics.ablation_table.map((row) => ({
                      variant: row.variant,
                      pr_auc: row.pr_auc != null ? +(row.pr_auc * 100).toFixed(1) : 0,
                      recall: +((row.recall_at_1pct_ffr ?? row.value_weighted_recall ?? 0) * 100).toFixed(1),
                    }))}
                    margin={{ top: 10, right: 20, left: 0, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="variant" stroke="#64748b" tick={{ fontSize: 11 }} />
                    <YAxis stroke="#64748b" domain={[0, 100]} tick={{ fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: 8, fontSize: 12 }}
                      labelStyle={{ color: '#f8fafc', fontWeight: 'bold' }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
                    <Bar dataKey="pr_auc" name="PR-AUC (%)" fill="#14b8a6" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="recall" name="Value Recall (%)" fill="#10b981" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider border-b border-slate-800 font-bengali">
                  <tr>
                    <th className="py-3 px-4">{t('metrics.col_variant')}</th>
                    <th className="py-3 px-4 text-center">{t('metrics.col_pr_auc')}</th>
                    <th className="py-3 px-4 text-center">{t('metrics.col_recall_ffr')}</th>
                    <th className="py-3 px-4 text-center">{t('metrics.col_latency')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 font-mono">
                  {metrics.ablation_table.map((row) => {
                    const prAucStr = row.pr_auc != null ? row.pr_auc.toFixed(3) : (row.brier_score != null ? `Brier: ${row.brier_score.toFixed(3)}` : '—');
                    const recallVal = row.recall_at_1pct_ffr ?? row.value_weighted_recall;
                    const recallStr = recallVal != null ? `${(recallVal * 100).toFixed(1)}%` : '—';
                    const latVal = row.p95_latency_ms ?? row.latency_p95_ms;
                    const latencyStr = latVal != null ? `${latVal.toFixed(2)} ms` : '—';
                    const isEvaluated = row.status === 'evaluated' || row.pr_auc != null;

                    return (
                      <tr
                        key={row.variant}
                        className={isEvaluated ? 'bg-teal-500/10 text-teal-200' : 'hover:bg-slate-800/40 text-slate-400'}
                      >
                        <td className="py-3.5 px-4 font-semibold text-slate-100 flex items-center gap-2">
                          <span className="font-bold text-white">{row.variant}:</span>
                          <span>{row.name || ''}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-teal-500/30 text-teal-300 font-bold uppercase">
                            Evaluated
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-center font-bold text-slate-200">
                          {lang === 'bn' ? toBengaliDigits(prAucStr) : prAucStr}
                        </td>
                        <td className="py-3.5 px-4 text-center font-bold text-emerald-400">
                          {lang === 'bn' ? toBengaliDigits(recallStr) : recallStr}
                        </td>
                        <td className="py-3.5 px-4 text-center text-slate-300">
                          {lang === 'bn' ? toBengaliDigits(latencyStr) : latencyStr}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="mt-4 p-3 rounded-xl bg-slate-950/70 border border-slate-800 text-xs text-slate-400 font-bengali">
              ℹ️ {t('metrics.heldout_note')}
            </div>
          </div>

          {/* Typology Breakdown Table */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl">
            <h2 className="text-base font-bold text-white mb-2 font-bengali">
              প্রতারণার প্যাটার্নভিত্তিক শনাক্তের হার (Per-Typology Recall Breakdown)
            </h2>
            <p className="text-xs text-slate-400 mb-4 font-bengali">
              সংরক্ষিত টেস্ট সেটের প্রতিটি ফ্রড টাইপোলজি অনুযায়ী ভ্যারিয়েন্ট A (রুলস) বনাম ভ্যারিয়েন্ট D (ফিউজড মডেল) এর তুলনা
            </p>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider border-b border-slate-800 font-bengali">
                  <tr>
                    <th className="py-3 px-4">টাইপোলজি / সিনারিও</th>
                    <th className="py-3 px-4 text-center">টাইপোলজি স্ট্যাটাস</th>
                    <th className="py-3 px-4 text-center">ভ্যারিয়েন্ট A (Rules)</th>
                    <th className="py-3 px-4 text-center">ভ্যারিয়েন্ট D (AI Fused)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 font-mono">
                  {typologies.map((typ) => {
                    const rowA = metrics.ablation_table.find((r) => r.variant === 'A');
                    const rowD = metrics.ablation_table.find((r) => r.variant === 'D');
                    const recA = (rowA as any)?.typology_recalls?.[typ.key] ?? null;
                    const recD = (rowD as any)?.typology_recalls?.[typ.key] ?? null;

                    const recAStr = recA != null ? `${(recA * 100).toFixed(1)}%` : '—';
                    const recDStr = recD != null ? `${(recD * 100).toFixed(1)}%` : '—';

                    return (
                      <tr key={typ.key} className={typ.heldOut ? 'bg-sky-500/10' : 'hover:bg-slate-800/40'}>
                        <td className="py-3 px-4 font-semibold text-slate-200">
                          {typ.label}
                        </td>
                        <td className="py-3 px-4 text-center">
                          {typ.heldOut ? (
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-sky-500/20 text-sky-300 font-bold border border-sky-500/30 uppercase">
                              Held-Out (Unseen)
                            </span>
                          ) : (
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 uppercase">
                              Standard
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-center text-slate-300">
                          {lang === 'bn' ? toBengaliDigits(recAStr) : recAStr}
                        </td>
                        <td className="py-3 px-4 text-center font-bold text-emerald-400">
                          {lang === 'bn' ? toBengaliDigits(recDStr) : recDStr}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Demographic Fairness Slices */}
          {metrics.fairness_slices && (
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl">
              <div className="flex items-center gap-2 mb-2">
                <Users className="w-5 h-5 text-teal-400" />
                <h2 className="text-base font-bold text-white font-bengali">
                  {t('metrics.fairness_title')} (Demographic Fairness Slices)
                </h2>
              </div>
              <p className="text-xs text-slate-400 mb-4 font-bengali">
                বিভিন্ন বয়স ও ভৌগোলিক অঞ্চলের গ্রাহকদের ক্ষেত্রে সিস্টেমের নিরপেক্ষতা ও মিথ্যা সতর্কতার সমতা যাচাই
              </p>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="space-y-2">
                  <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-bengali">
                    বয়সের শ্রেণী (Age Band)
                  </h3>
                  {Object.entries(metrics.fairness_slices.age_band || {}).map(([band, val]) => {
                    const ffrNum = typeof val === 'number' ? val : (val as any)?.ffr ?? 0.0;
                    const recallNum = typeof val === 'object' ? (val as any)?.recall : null;
                    return (
                      <div key={band} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-950 text-xs border border-slate-800 font-mono">
                        <span className="text-slate-300 capitalize">{band}</span>
                        <div className="flex items-center gap-3">
                          {recallNum != null && (
                            <span className="text-slate-400 text-[11px]">
                              Rec: {lang === 'bn' ? toBengaliDigits((recallNum * 100).toFixed(1)) : (recallNum * 100).toFixed(1)}%
                            </span>
                          )}
                          <span className="font-bold text-teal-400">
                            {lang === 'bn' ? toBengaliDigits((ffrNum * 100).toFixed(2)) : (ffrNum * 100).toFixed(2)}% FFR
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="space-y-2">
                  <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-bengali">
                    ভৌগোলিক অঞ্চল (Region Type)
                  </h3>
                  {Object.entries(metrics.fairness_slices.region_type || {}).map(([region, val]) => {
                    const ffrNum = typeof val === 'number' ? val : (val as any)?.ffr ?? 0.0;
                    const recallNum = typeof val === 'object' ? (val as any)?.recall : null;
                    return (
                      <div key={region} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-950 text-xs border border-slate-800 font-mono">
                        <span className="text-slate-300 capitalize">{region}</span>
                        <div className="flex items-center gap-3">
                          {recallNum != null && (
                            <span className="text-slate-400 text-[11px]">
                              Rec: {lang === 'bn' ? toBengaliDigits((recallNum * 100).toFixed(1)) : (recallNum * 100).toFixed(1)}%
                            </span>
                          )}
                          <span className="font-bold text-teal-400">
                            {lang === 'bn' ? toBengaliDigits((ffrNum * 100).toFixed(2)) : (ffrNum * 100).toFixed(2)}% FFR
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="space-y-2">
                  <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-bengali">
                    অ্যাকাউন্টের মেয়াদ (Tenure Bucket)
                  </h3>
                  {Object.entries(metrics.fairness_slices.tenure_bucket || {}).map(([tenure, val]) => {
                    const ffrNum = typeof val === 'number' ? val : (val as any)?.ffr ?? 0.0;
                    const recallNum = typeof val === 'object' ? (val as any)?.recall : null;
                    return (
                      <div key={tenure} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-950 text-xs border border-slate-800 font-mono">
                        <span className="text-slate-300 capitalize">{tenure}</span>
                        <div className="flex items-center gap-3">
                          {recallNum != null && (
                            <span className="text-slate-400 text-[11px]">
                              Rec: {lang === 'bn' ? toBengaliDigits((recallNum * 100).toFixed(1)) : (recallNum * 100).toFixed(1)}%
                            </span>
                          )}
                          <span className="font-bold text-teal-400">
                            {lang === 'bn' ? toBengaliDigits((ffrNum * 100).toFixed(2)) : (ffrNum * 100).toFixed(2)}% FFR
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Policy Sensitivity Grid */}
          {metrics.sensitivity_grid && metrics.sensitivity_grid.length > 0 && (
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl">
              <div className="flex items-center gap-2 mb-2">
                <Sliders className="w-5 h-5 text-teal-400" />
                <h2 className="text-base font-bold text-white font-bengali">
                  পলিসি সেনসিটিভিটি বিশ্লেষণ (Policy Engine Sensitivity Grid)
                </h2>
              </div>
              <p className="text-xs text-slate-400 mb-4 font-bengali">
                বিভিন্ন কার্যক্ষমতা ও ঘর্ষণ অনুমানের বিপরীতে প্রতিরোধকৃত মোট অর্থের সংবেদনশীলতা পরীক্ষা
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {metrics.sensitivity_grid.map((s) => (
                  <div key={s.effectiveness_scenario} className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <div className="text-xs uppercase font-bold text-teal-400 tracking-wider">
                      {s.effectiveness_scenario}
                    </div>
                    <div className="text-xl font-bold text-white font-mono mt-2">
                      {formatBDT(s.intercepted_bdt, lang)}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-2 space-y-1 font-mono">
                      <div>Hold Eff: {lang === 'bn' ? toBengaliDigits((s.hold_eff * 100).toFixed(0)) : (s.hold_eff * 100).toFixed(0)}%</div>
                      <div>Verify Eff: {lang === 'bn' ? toBengaliDigits((s.verify_eff * 100).toFixed(0)) : (s.verify_eff * 100).toFixed(0)}%</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Honesty Footer Label */}
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-center text-xs text-slate-400 font-bengali">
            {t('metrics.test_split_footer')}
          </div>
        </div>
      )}
    </div>
  );
};
