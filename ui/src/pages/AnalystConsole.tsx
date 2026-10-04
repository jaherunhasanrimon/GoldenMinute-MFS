import React, { useEffect, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { api, AlertDetail, AlertSummary, GraphResponse } from '../api/client';
import { useI18n } from '../locales/i18n';
import { formatBDT, formatTimeLeft, toBengaliDigits } from '../utils/format';
import {
  Activity,
  ShieldAlert,
  CheckCircle,
  ArrowUpRight,
  X,
  Clock,
  DollarSign,
  Filter,
  RefreshCw,
  Network,
  History,
  AlertTriangle,
} from 'lucide-react';

export const AnalystConsole: React.FC = () => {
  const { lang, t } = useI18n();
  const [alerts, setAlerts] = useState<AlertSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [selectedAlert, setSelectedAlert] = useState<AlertDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [releaseNote, setReleaseNote] = useState('');
  const [noteError, setNoteError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Local Wallet Graph state for detail drawer
  const [graphData, setGraphData] = useState<GraphResponse | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);

  // Poll every 3 seconds as required by ARCHITECTURE.md and PHASES.md
  useEffect(() => {
    let mounted = true;

    const fetchAlerts = () => {
      const filter = statusFilter === 'all' ? undefined : statusFilter;
      api.getAlerts(filter)
        .then((data) => {
          if (!mounted) return;
          setAlerts(data.alerts);
          setError(null);
        })
        .catch((err) => {
          if (!mounted) return;
          setError(err.message || 'Failed to fetch alerts');
        })
        .finally(() => {
          if (mounted) setLoading(false);
        });
    };

    fetchAlerts();
    const interval = setInterval(fetchAlerts, 3000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [statusFilter]);

  const handleOpenDetail = async (alertId: string) => {
    setDetailLoading(true);
    setActionSuccess(null);
    setNoteError(null);
    setGraphData(null);

    try {
      const detail = await api.getAlertDetail(alertId);
      setSelectedAlert(detail);

      // Load local wallet graph for the recipient wallet
      if (detail.recipient_wallet_id) {
        setGraphLoading(true);
        api.getWalletGraph(detail.recipient_wallet_id)
          .then((g) => setGraphData(g))
          .catch(() => setGraphData(null))
          .finally(() => setGraphLoading(false));
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDecision = async (action: 'approve' | 'release' | 'escalate') => {
    if (!selectedAlert) return;

    if (action === 'release' && !releaseNote.trim()) {
      setNoteError(
        lang === 'bn'
          ? 'লেনদেন অবমুক্ত করার জন্য অ্যানালিস্ট নোট উল্লেখ করা বাধ্যতামূলক।'
          : 'Analyst note is strictly required to release a held transaction.'
      );
      return;
    }

    try {
      await api.decideAlert(selectedAlert.alert_id, action, releaseNote.trim());
      setActionSuccess(
        lang === 'bn'
          ? `অ্যালার্ট #${selectedAlert.alert_id}-এ '${action}' পদক্ষেপ সফলভাবে রেকর্ড করা হয়েছে।`
          : `Alert #${selectedAlert.alert_id} successfully updated with action: ${action}.`
      );

      // Update local alert in list
      setAlerts((prev) =>
        prev.map((a) =>
          a.alert_id === selectedAlert.alert_id
            ? { ...a, status: action === 'approve' || action === 'release' ? 'resolved' : 'in_review' }
            : a
        )
      );
      setSelectedAlert(null);
      setReleaseNote('');
      setNoteError(null);
    } catch (err: any) {
      alert(`Action failed: ${err.message}`);
    }
  };

  const totalMoneyAtRisk = alerts.reduce(
    (acc, curr) => acc + (curr.status === 'open' ? curr.money_at_risk : 0),
    0
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Header & Live Polling Status */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2 font-bengali">
            <Activity className="w-6 h-6 text-teal-400" />
            {t('analyst.title')}
          </h1>
          <p className="text-sm text-slate-400 mt-1 font-bengali">
            {t('analyst.subtitle')}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-teal-400 font-mono">
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-teal-400" />
            <span className="font-bengali">{t('analyst.auto_refresh')}</span>
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase font-bengali">
              {t('analyst.queue_count')}
            </span>
            <ShieldAlert className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-white mt-1 font-mono">
            {lang === 'bn'
              ? toBengaliDigits(alerts.filter((a) => a.status === 'open').length)
              : alerts.filter((a) => a.status === 'open').length}
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase font-bengali">
              {t('analyst.money_at_risk')}
            </span>
            <DollarSign className="w-4 h-4 text-rose-400" />
          </div>
          <div className="text-2xl font-bold text-rose-400 mt-1 font-mono">
            {formatBDT(totalMoneyAtRisk, lang)}
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase font-bengali">
              গোল্ডেন উইন্ডো লক্ষ্যমাত্রা
            </span>
            <Clock className="w-4 h-4 text-teal-400" />
          </div>
          <div className="text-2xl font-bold text-teal-400 mt-1 font-mono">
            {lang === 'bn' ? '< ৩০ মি.' : '< 30 min'}
          </div>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 mb-4 overflow-x-auto pb-2">
        <Filter className="w-4 h-4 text-slate-500 mr-1" />
        {[
          { key: 'all', label: t('analyst.filter_all') },
          { key: 'open', label: t('analyst.filter_open') },
          { key: 'in_review', label: t('analyst.filter_in_review') },
          { key: 'resolved', label: t('analyst.filter_resolved') },
        ].map((f) => (
          <button
            key={f.key}
            onClick={() => setStatusFilter(f.key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              statusFilter === f.key
                ? 'bg-teal-500/20 text-teal-300 border border-teal-500/40'
                : 'bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200'
            } font-bengali`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Action Notification */}
      {actionSuccess && (
        <div className="mb-4 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between font-bengali">
          <span>{actionSuccess}</span>
          <button onClick={() => setActionSuccess(null)}>
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Table Container */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl overflow-hidden shadow-xl backdrop-blur-sm">
        {loading ? (
          <div className="py-20 text-center text-slate-400 animate-pulse font-bengali">
            লোড হচ্ছে...
          </div>
        ) : error ? (
          <div className="p-6 text-center text-rose-300 text-sm font-bengali">
            {error}
          </div>
        ) : alerts.length === 0 ? (
          <div className="py-20 text-center text-slate-400 font-bengali">
            {t('analyst.empty_state')}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-300">
              <thead className="bg-slate-950/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800 font-bengali">
                <tr>
                  <th className="py-3 px-4">{t('analyst.th_alert_id')}</th>
                  <th className="py-3 px-4">{t('analyst.th_sender')}</th>
                  <th className="py-3 px-4">{t('analyst.th_recipient')}</th>
                  <th className="py-3 px-4 text-right">{t('analyst.th_amount')}</th>
                  <th className="py-3 px-4 text-center">{t('analyst.th_priority')}</th>
                  <th className="py-3 px-4 text-center">{t('analyst.th_time_left')}</th>
                  <th className="py-3 px-4 text-center">{t('analyst.th_status')}</th>
                  <th className="py-3 px-4 text-right">{t('analyst.th_action')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                {alerts.map((alert) => (
                  <tr key={alert.alert_id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3.5 px-4 font-bold text-teal-400">
                      {alert.alert_id}
                    </td>
                    <td className="py-3.5 px-4 text-slate-200">
                      {alert.sender_wallet_id}
                    </td>
                    <td className="py-3.5 px-4 text-amber-300 font-semibold">
                      {alert.recipient_wallet_id}
                    </td>
                    <td className="py-3.5 px-4 text-right font-bold text-white">
                      {formatBDT(alert.amount_bdt, lang)}
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <span className="px-2 py-0.5 rounded-full font-bold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                        {lang === 'bn' ? toBengaliDigits(alert.priority.toFixed(1)) : alert.priority.toFixed(1)}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-center text-slate-300">
                      <span className="inline-flex items-center gap-1 text-amber-400 font-bold">
                        <Clock className="w-3 h-3" />
                        {formatTimeLeft(alert.deadline_ts, lang)}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <span
                        className={`px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${
                          alert.status === 'open'
                            ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                            : alert.status === 'in_review'
                            ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                            : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        }`}
                      >
                        {alert.status}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => handleOpenDetail(alert.alert_id)}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-teal-500/20 hover:bg-teal-500/30 text-teal-300 font-medium text-xs border border-teal-500/30 transition-all font-bengali"
                      >
                        <span>{t('analyst.view_detail')}</span>
                        <ArrowUpRight className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail Drawer Modal */}
      {selectedAlert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full max-h-[92vh] overflow-y-auto shadow-2xl p-6">
            {/* Drawer Header */}
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div className="flex items-center gap-3">
                <ShieldAlert className="w-6 h-6 text-rose-400" />
                <div>
                  <h3 className="text-lg font-bold text-white font-bengali">
                    {t('analyst.detail_title')} #{selectedAlert.alert_id}
                  </h3>
                  <span className="text-xs text-slate-400 font-mono">
                    {detailLoading ? 'Updating details...' : `Txn: ${selectedAlert.txn_id} | Deadline: ${formatTimeLeft(selectedAlert.deadline_ts, lang)}`}
                  </span>
                </div>
              </div>
              <button
                onClick={() => setSelectedAlert(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-5 py-4">
              {/* Score & Money at Risk Banner */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
                  <div className="text-xs text-slate-400 font-bengali">রিস্ক স্কোর / অ্যাকশন</div>
                  <div className="text-lg font-bold text-rose-400 font-mono mt-1">
                    {lang === 'bn' ? toBengaliDigits((selectedAlert.risk_score * 100).toFixed(0)) : (selectedAlert.risk_score * 100).toFixed(0)}% — {selectedAlert.action.toUpperCase()}
                  </div>
                </div>
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800">
                  <div className="text-xs text-slate-400 font-bengali">ঝুঁকিপূর্ণ অর্থ</div>
                  <div className="text-lg font-bold text-white font-mono mt-1">
                    {formatBDT(selectedAlert.amount_bdt, lang)}
                  </div>
                </div>
              </div>

              {/* Bilingual Case Narrative */}
              {selectedAlert.narrative && (
                <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800">
                  <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2 font-bengali">
                    {t('analyst.narrative_title')}
                  </h4>
                  <p className="text-xs text-slate-200 leading-relaxed font-bengali">
                    {lang === 'bn' ? selectedAlert.narrative.bn : selectedAlert.narrative.en}
                  </p>
                </div>
              )}

              {/* Reason Codes */}
              <div>
                <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2 font-bengali">
                  চিহ্নিত ঝুঁকি নির্দেশক (SHAP Attribution)
                </h4>
                <div className="space-y-1.5">
                  {selectedAlert.reason_codes.map((rc) => (
                    <div
                      key={rc.code}
                      className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-950 text-xs font-mono border border-slate-800"
                    >
                      <span className="text-teal-400 font-medium">{rc.code}</span>
                      <span className="text-slate-400">
                        {lang === 'bn' ? toBengaliDigits((rc.weight * 100).toFixed(0)) : (rc.weight * 100).toFixed(0)}% contribution
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Local Wallet Graph Visualization */}
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Network className="w-4 h-4 text-teal-400" />
                    <h4 className="text-xs font-semibold text-white uppercase tracking-wider font-bengali">
                      লোকাল ওয়ালেট গ্রাফ (Local Wallet Graph — 2-Hop Connectivity)
                    </h4>
                  </div>
                  {graphData && (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-teal-300 font-mono">
                      {graphData.nodes.length} nodes, {graphData.edges.length} edges
                    </span>
                  )}
                </div>

                {graphLoading ? (
                  <div className="py-8 text-center text-xs text-slate-400 animate-pulse font-bengali">
                    গ্রাফ ডাটা লোড হচ্ছে...
                  </div>
                ) : graphData && graphData.nodes.length > 0 ? (
                  <div className="space-y-3">
                    {/* Interactive 2D Force-Directed Graph */}
                    <div className="rounded-xl overflow-hidden border border-slate-800 bg-slate-950 flex justify-center" style={{ height: 200 }}>
                      <ForceGraph2D
                        graphData={{
                          nodes: graphData.nodes.map((n) => ({
                            ...n,
                            val: n.is_mule ? 7 : (n.id === selectedAlert.recipient_wallet_id ? 6 : 4),
                          })),
                          links: graphData.edges.map((e) => ({
                            source: e.source,
                            target: e.target,
                            amount_bdt: e.amount_bdt,
                          })),
                        }}
                        width={460}
                        height={200}
                        backgroundColor="#020617"
                        nodeColor={(node: any) =>
                          node.is_mule
                            ? '#f43f5e'
                            : node.id === selectedAlert.recipient_wallet_id
                            ? '#f59e0b'
                            : node.type === 'device'
                            ? '#38bdf8'
                            : '#14b8a6'
                        }
                        nodeLabel={(node: any) => `${node.label || node.id} (${node.type})${node.is_mule ? ' - CONFIRMED MULE' : ''}`}
                        linkColor={() => '#334155'}
                        linkDirectionalParticles={2}
                        linkDirectionalParticleSpeed={0.005}
                        linkDirectionalParticleWidth={2}
                        linkDirectionalParticleColor={() => '#14b8a6'}
                      />
                    </div>

                    {/* Visual node cluster preview */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {graphData.nodes.slice(0, 6).map((node) => (
                        <div
                          key={node.id}
                          className={`p-2 rounded-lg border text-xs font-mono ${
                            node.is_mule
                              ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                              : node.id === selectedAlert.recipient_wallet_id
                              ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                              : 'bg-slate-900 border-slate-800 text-slate-300'
                          }`}
                        >
                          <div className="flex items-center justify-between text-[10px]">
                            <span className="uppercase text-slate-400">{node.type}</span>
                            {node.is_mule && (
                              <span className="px-1 py-0.2 rounded bg-rose-500/20 text-rose-400 font-bold">
                                MULE
                              </span>
                            )}
                          </div>
                          <div className="font-bold truncate mt-0.5">{node.label || node.id}</div>
                        </div>
                      ))}
                    </div>

                    {/* Edge transaction preview */}
                    {graphData.edges.length > 0 && (
                      <div className="text-[11px] text-slate-400 border-t border-slate-800/80 pt-2 font-mono flex items-center justify-between">
                        <span>Cluster Flow: {graphData.edges[0].source} → {graphData.edges[0].target}</span>
                        <span className="text-teal-400 font-bold">{formatBDT(graphData.edges[0].amount_bdt, lang)}</span>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="py-4 text-center text-xs text-slate-400 font-bengali">
                    কোনো বাহ্যিক রিং সংযোগ নেই (Single-node topology)
                  </div>
                )}
              </div>

              {/* Key Evidence */}
              {selectedAlert.evidence && (
                <div>
                  <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2 font-bengali">
                    {t('analyst.evidence_title')}
                  </h4>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs font-mono">
                    {Object.entries(selectedAlert.evidence).slice(0, 9).map(([key, val]) => (
                      <div key={key} className="p-2.5 rounded-lg bg-slate-950 border border-slate-800">
                        <div className="text-slate-400 text-[10px] truncate">{key}</div>
                        <div className="text-white font-bold mt-0.5 truncate">{String(val)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Audit Trail / Actions Taken */}
              {selectedAlert.actions_taken && selectedAlert.actions_taken.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <History className="w-3.5 h-3.5 text-teal-400" />
                    <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-bengali">
                      পূর্ববর্তী পদক্ষেপ ও অডিট হিস্টোরি (Audit Trail)
                    </h4>
                  </div>
                  <div className="space-y-1.5">
                    {selectedAlert.actions_taken.map((act, idx) => (
                      <div
                        key={idx}
                        className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono flex items-center justify-between"
                      >
                        <div>
                          <span className="font-bold text-teal-400 uppercase">{act.action_taken}</span>
                          <span className="text-slate-400 ml-2">by {act.analyst_id}</span>
                          {act.note && <p className="text-[11px] text-slate-300 mt-0.5">{act.note}</p>}
                        </div>
                        <span className="text-slate-400 text-[10px]">
                          {new Date(act.ts).toLocaleTimeString()}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Release Note Input */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5 font-bengali">
                  অ্যানালিস্ট নোট (Release করার জন্য বাধ্যতামূলক)
                </label>
                <textarea
                  value={releaseNote}
                  onChange={(e) => {
                    setReleaseNote(e.target.value);
                    if (e.target.value.trim()) setNoteError(null);
                  }}
                  placeholder={t('analyst.release_note_placeholder')}
                  className={`w-full bg-slate-950 border rounded-xl p-3 text-xs text-white focus:outline-none focus:border-teal-500 font-bengali ${
                    noteError ? 'border-rose-500 ring-1 ring-rose-500' : 'border-slate-700'
                  }`}
                  rows={2}
                />
                {noteError && (
                  <p className="text-rose-400 text-xs mt-1 font-bengali flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" />
                    <span>{noteError}</span>
                  </p>
                )}
              </div>
            </div>

            {/* Analyst Actions */}
            <div className="pt-4 border-t border-slate-800 flex flex-wrap gap-2 justify-end">
              <button
                onClick={() => handleDecision('escalate')}
                className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium font-bengali border border-slate-700 transition-colors"
              >
                {t('analyst.action_escalate')}
              </button>
              <button
                onClick={() => handleDecision('release')}
                className="px-3.5 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium font-bengali shadow transition-colors"
              >
                {t('analyst.action_release')}
              </button>
              <button
                onClick={() => handleDecision('approve')}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-medium font-bengali flex items-center gap-1.5 shadow transition-colors"
              >
                <CheckCircle className="w-3.5 h-3.5" />
                {t('analyst.action_approve')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
