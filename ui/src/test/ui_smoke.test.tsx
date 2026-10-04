import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { App } from '../App';

describe('GoldenMinutes UI Smoke Tests', () => {
  beforeEach(() => {
    // Clear localStorage
    localStorage.clear();

    // Mock global fetch to return stub fixtures matching API
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const urlStr = String(url);
      const headers = new Headers();
      headers.set('X-GM-Stub', '1');

      if (urlStr.includes('/v1/demo/accounts')) {
        return Promise.resolve(new Response(JSON.stringify({
          senders: [
            { wallet_id: 'W01928', customer_id: 'C10001', name: 'Karim Ahmed', balance_bdt: 45000, persona: 'salaried', description: 'Regular salary' }
          ],
          recipients: [
            { wallet_id: 'W08371', customer_id: 'C90001', name: 'Mule W08371', balance_bdt: 3400, persona: 'mule', description: 'Fresh wallet burst' }
          ]
        }), { status: 200, headers }));
      }

      if (urlStr.includes('/v1/alerts')) {
        return Promise.resolve(new Response(JSON.stringify({
          alerts: [
            { alert_id: 'A1001', decision_id: 'D9001', txn_id: 'TXN-9801', status: 'open', priority: 0.92, money_at_risk: 25000, deadline_ts: '2026-10-04T12:00:00Z', created_at: '2026-10-04T11:40:00Z', sender_wallet_id: 'W01928', recipient_wallet_id: 'W08371', amount_bdt: 25000 }
          ],
          total: 1
        }), { status: 200, headers }));
      }

      if (urlStr.includes('/v1/metrics')) {
        return Promise.resolve(new Response(JSON.stringify({
          fraud_value_intercepted_bdt: 4285000,
          false_friction_rate: 0.0078,
          median_decision_time_ms: 28.4,
          p95_decision_time_ms: 64.2,
          ablation_table: [
            { variant: 'A: Rules Baseline', pr_auc: 0.46, recall_at_1pct_ffr: 0.52, latency_p95_ms: 12.0 }
          ],
          total_scored: 1000,
          total_alerts: 10
        }), { status: 200, headers }));
      }

      return Promise.resolve(new Response(JSON.stringify({ status: 'ok' }), { status: 200, headers }));
    }));
  });

  it('renders navbar, branding, and demo-data badge', async () => {
    render(<App />);

    expect(screen.getByText('GoldenMinutes')).toBeInTheDocument();
    expect(screen.getByText('upay')).toBeInTheDocument();

    const badge = await screen.findByTestId('demo-data-badge');
    expect(badge).toBeInTheDocument();
  });

  it('renders customer demo screen by default', async () => {
    render(<App />);

    // Customer page elements
    expect(await screen.findByText(/সেন্ড মানি সিমুলেশন|Send Money Simulation/)).toBeInTheDocument();
  });

  it('toggles language between Bangla and English', async () => {
    render(<App />);

    const langBtn = screen.getByRole('button', { name: /Toggle language/i });

    // Initially Bangla, toggle button shows English
    expect(langBtn).toHaveTextContent('English');

    // Click to switch to English
    fireEvent.click(langBtn);

    await waitFor(() => {
      expect(screen.getByText('Customer Demo')).toBeInTheDocument();
      expect(langBtn).toHaveTextContent('বাংলা');
    });

    // Click to switch back to Bangla
    fireEvent.click(langBtn);

    await waitFor(() => {
      expect(screen.getByText('গ্রাহক ডেমো')).toBeInTheDocument();
      expect(langBtn).toHaveTextContent('English');
    });
  });

  it('navigates to analyst console and metrics pages', async () => {
    render(<App />);

    // Click on Analyst Console link
    const analystLink = screen.getByRole('link', { name: /অ্যানালিস্ট কনসোল|Analyst Console/i });
    fireEvent.click(analystLink);

    expect(await screen.findByText(/অ্যানালিস্ট প্রায়োরিটি কিউ|Analyst Priority Queue/)).toBeInTheDocument();

    // Click on Metrics link
    const metricsLink = screen.getByRole('link', { name: /মেট্রিক্স ও মূল্যায়ন|Metrics & Evaluation/i });
    fireEvent.click(metricsLink);

    expect(await screen.findByText(/সিস্টেম কার্যক্ষমতা ও অ্যাবলেশন|System Performance & Ablation/)).toBeInTheDocument();
  });
});
