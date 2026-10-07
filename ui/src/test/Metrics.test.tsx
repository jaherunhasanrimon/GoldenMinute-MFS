import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { I18nProvider } from '../locales/i18n';
import { Metrics } from '../pages/Metrics';

const renderMetrics = () => {
  return render(
    <I18nProvider>
      <Metrics />
    </I18nProvider>
  );
};

describe('Metrics Component Tests', () => {
  beforeEach(() => {
    localStorage.clear();

    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const urlStr = String(url);

      if (urlStr.includes('/v1/metrics')) {
        return Promise.resolve(new Response(JSON.stringify({
          fraud_value_intercepted_bdt: 4447777.56,
          false_friction_rate: 0.0045,
          median_decision_time_ms: 0.8,
          p95_decision_time_ms: 2.25,
          ablation_table: [
            { variant: 'A', name: 'Rules baseline', status: 'evaluated', pr_auc: 0.114, recall_at_1pct_ffr: 0.5436, latency_p95_ms: 0.75, typology_recalls: { agent_collusion: 1.0, impersonation_scam: 0.23 } },
            { variant: 'B', name: 'LightGBM (no graph)', status: 'evaluated', pr_auc: 0.9935, recall_at_1pct_ffr: 0.9897, latency_p95_ms: 1.5, typology_recalls: { agent_collusion: 0.98, impersonation_scam: 0.98 } },
            { variant: 'C', name: 'LightGBM + Graph', status: 'evaluated', pr_auc: 0.9935, recall_at_1pct_ffr: 0.9897, latency_p95_ms: 1.8, typology_recalls: { agent_collusion: 0.98, impersonation_scam: 0.98 } },
            { variant: 'D', name: 'Fused (C + Anomaly)', status: 'evaluated', pr_auc: 0.9955, recall_at_1pct_ffr: 0.9897, latency_p95_ms: 2.25, typology_recalls: { agent_collusion: 0.9836, impersonation_scam: 0.9885 } },
            { variant: 'E', name: 'LightGBM + Graph + GNN', status: 'evaluated', pr_auc: 0.9960, recall_at_1pct_ffr: 0.9910, latency_p95_ms: 2.45, typology_recalls: { agent_collusion: 0.9850, impersonation_scam: 0.9900 } },
            { variant: 'F', name: 'GNN score only (diagnostic)', status: 'evaluated', pr_auc: 0.1500, recall_at_1pct_ffr: 0.1000, latency_p95_ms: 1.20, typology_recalls: { agent_collusion: 0.1000, impersonation_scam: 0.1000 } }
          ],
          held_out_typology_recall: 0.9836,
          fairness_slices: {
            age_band: {
              senior: { ffr: 0.0, recall: 0.991 },
              middle: { ffr: 0.0, recall: 0.992 },
              young: { ffr: 0.0, recall: 1.0 }
            },
            region_type: {
              urban: { ffr: 0.0, recall: 0.992 },
              rural: { ffr: 0.0, recall: 1.0 }
            },
            tenure_bucket: {
              '1m+': { ffr: 0.0, recall: 0.992 },
              '<1w': { ffr: 0.0, recall: 1.0 }
            }
          },
          sensitivity_grid: [
            { effectiveness_scenario: 'conservative', hold_eff: 0.85, verify_eff: 0.5, intercepted_bdt: 3979590.45 },
            { effectiveness_scenario: 'baseline', hold_eff: 0.95, verify_eff: 0.7, intercepted_bdt: 4447777.56 },
            { effectiveness_scenario: 'optimistic', hold_eff: 0.99, verify_eff: 0.85, intercepted_bdt: 4635052.41 }
          ],
          total_scored: 120583,
          total_alerts: 310
        }), { status: 200 }));
      }

      return Promise.resolve(new Response(JSON.stringify({ status: 'ok' }), { status: 200 }));
    }));
  });

  it('renders headline KPI cards with intercepted amount and latency', async () => {
    renderMetrics();
    await waitFor(() => {
      expect(screen.getByText(/সিস্টেম কার্যক্ষমতা ও অ্যাবলেশন/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/প্রতিরোধকৃত অর্থের পরিমাণ/i)).toBeInTheDocument();
    expect(screen.getByText(/মিথ্যা সতর্কতার হার/i)).toBeInTheDocument();
    expect(screen.getByText(/p95 সময়কাল/i)).toBeInTheDocument();
    expect(screen.getByText(/অদেখা প্যাটার্ন শনাক্তের হার/i)).toBeInTheDocument();
  });

  it('renders Variant A–F ablation comparison table', async () => {
    renderMetrics();
    await waitFor(() => {
      expect(screen.getByText(/মডেল তুলনা \(ভ্যারিয়েন্ট A–[DF]\)/i)).toBeInTheDocument();
    });

    expect(screen.getByText('A:')).toBeInTheDocument();
    expect(screen.getByText('B:')).toBeInTheDocument();
    expect(screen.getByText('C:')).toBeInTheDocument();
    expect(screen.getByText('D:')).toBeInTheDocument();
    expect(screen.getByText('E:')).toBeInTheDocument();
    expect(screen.getByText('F:')).toBeInTheDocument();
  });

  it('renders per-typology breakdown table highlighting agent_collusion as held-out', async () => {
    renderMetrics();
    await waitFor(() => {
      expect(screen.getByText(/প্রতারণার প্যাটার্নভিত্তিক শনাক্তের হার/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Agent Collusion \(Held-Out Typology\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Held-Out \(Unseen\)/i)).toBeInTheDocument();
  });

  it('renders demographic fairness slices and policy sensitivity grid', async () => {
    renderMetrics();
    await waitFor(() => {
      expect(screen.getByText(/ন্যায্যতা ও বৈষম্যহীনতা বিশ্লেষণ/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/বয়সের শ্রেণী \(Age Band\)/i)).toBeInTheDocument();
    expect(screen.getByText(/ভৌগোলিক অঞ্চল \(Region Type\)/i)).toBeInTheDocument();
    expect(screen.getByText(/অ্যাকাউন্টের মেয়াদ \(Tenure Bucket\)/i)).toBeInTheDocument();
    expect(screen.getByText(/পলিসি সেনসিটিভিটি বিশ্লেষণ/i)).toBeInTheDocument();
    expect(screen.getByText('conservative')).toBeInTheDocument();
    expect(screen.getByText('baseline')).toBeInTheDocument();
    expect(screen.getByText('optimistic')).toBeInTheDocument();
  });

  it('renders honest synthetic test split footer label', async () => {
    renderMetrics();
    await waitFor(() => {
      expect(screen.getByText(/সিন্থেটিক ডাটা, সংরক্ষিত টেস্ট সেট। টেস্ট সেটে কখনো টিউন করা হয়নি।/i)).toBeInTheDocument();
    });
  });
});
