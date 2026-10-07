import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { I18nProvider } from '../locales/i18n';
import { AuthProvider } from '../context/AuthContext';
import { AnalystConsole } from '../pages/AnalystConsole';

const renderAnalystConsole = () => {
  return render(
    <AuthProvider>
      <I18nProvider>
        <AnalystConsole />
      </I18nProvider>
    </AuthProvider>
  );
};

describe('AnalystConsole Component Tests', () => {
  beforeEach(() => {
    localStorage.clear();

    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      const urlStr = String(url);
      const method = init?.method || 'GET';

      if (urlStr.includes('/v1/auth/me') || urlStr.includes('/v1/auth/login')) {
        return Promise.resolve(new Response(JSON.stringify({
          access_token: 'mock-token',
          refresh_token: 'mock-refresh',
          token_type: 'bearer',
          expires_in: 3600,
          user: {
            user_id: 'USR-001',
            username: 'analyst_karim',
            full_name: 'Karim Rahman',
            role: 'analyst',
            is_active: true
          }
        }), { status: 200 }));
      }

      if (urlStr.includes('/v1/audit/verify')) {
        return Promise.resolve(new Response(JSON.stringify({
          valid: true,
          total_records: 12,
          genesis_hash: 'genesis-hash',
          last_hash: 'last-hash'
        }), { status: 200 }));
      }

      if (urlStr.includes('/v1/alerts') && !urlStr.includes('/v1/alerts/A1001') && method === 'GET') {
        return Promise.resolve(new Response(JSON.stringify({
          alerts: [
            {
              alert_id: 'A1001',
              decision_id: 'D9001',
              txn_id: 'TXN-9801',
              status: 'open',
              priority: 0.94,
              money_at_risk: 35000,
              deadline_ts: new Date(Date.now() + 25 * 60000).toISOString(),
              created_at: new Date().toISOString(),
              sender_wallet_id: 'W01928',
              recipient_wallet_id: 'W08371',
              amount_bdt: 35000
            }
          ],
          total: 1
        }), { status: 200 }));
      }

      if (urlStr.includes('/v1/alerts/A1001') && !urlStr.includes('/decision') && method === 'GET') {
        return Promise.resolve(new Response(JSON.stringify({
          alert_id: 'A1001',
          decision_id: 'D9001',
          txn_id: 'TXN-9801',
          status: 'open',
          priority: 0.94,
          money_at_risk: 35000,
          deadline_ts: new Date(Date.now() + 25 * 60000).toISOString(),
          created_at: new Date().toISOString(),
          risk_score: 0.94,
          action: 'hold',
          reason_codes: [
            { code: 'RECIPIENT_FAN_IN_BURST', weight: 0.65 },
            { code: 'AMOUNT_UNUSUAL_FOR_SENDER', weight: 0.35 }
          ],
          sender_wallet_id: 'W01928',
          recipient_wallet_id: 'W08371',
          amount_bdt: 35000,
          narrative: {
            bn: 'লেনদেন HOLD পদক্ষেপ গৃহীত হয়েছে: W01928 থেকে W08371 ওয়ালেটে ৩৫,০০০ টাকার স্থানান্তর। প্রাপক ওয়ালেট গত ১ ঘণ্টায় একাধিক ভিন্ন প্রেরক থেকে অর্থ গ্রহণ করেছে।',
            en: 'Transaction HOLD triggered: 35,000 BDT transfer from W01928 to W08371. Recipient wallet received funds from multiple senders in 1h.'
          },
          evidence: {
            recipient_unique_senders_1h: 4,
            recipient_unique_senders_24h: 9,
            amount_to_median_ratio: 3.5,
            recipient_pass_through_ratio_24h: 0.88
          },
          actions_taken: [
            {
              action_taken: 'flagged',
              analyst_id: 'system_ai',
              ts: new Date().toISOString(),
              note: 'Initial AI high-risk interception'
            }
          ]
        }), { status: 200 }));
      }

      if (urlStr.includes('/v1/graph/W08371')) {
        return Promise.resolve(new Response(JSON.stringify({
          wallet_id: 'W08371',
          nodes: [
            { id: 'W08371', label: 'W08371 (Target)', type: 'wallet', risk_score: 0.94, is_mule: true },
            { id: 'W01928', label: 'W01928 (Victim)', type: 'wallet', risk_score: 0.05, is_mule: false },
            { id: 'W01443', label: 'W01443 (Victim 2)', type: 'wallet', risk_score: 0.08, is_mule: false },
            { id: 'DEV_MULE_RING', label: 'Shared Device', type: 'device', risk_score: 0.85, is_mule: true }
          ],
          edges: [
            { source: 'W01928', target: 'W08371', amount_bdt: 35000, txn_count: 1 }
          ]
        }), { status: 200 }));
      }

      if (urlStr.includes('/v1/alerts/A1001/decision') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}'));
        return Promise.resolve(new Response(JSON.stringify({
          alert_id: 'A1001',
          status: 'resolved',
          action_taken: body.action,
          analyst_id: 'analyst_demo',
          ts: new Date().toISOString(),
          note: body.note
        }), { status: 200 }));
      }

      return Promise.resolve(new Response(JSON.stringify({ status: 'ok' }), { status: 200 }));
    }));
  });

  it('renders alert queue with priority, money at risk, and time left', async () => {
    renderAnalystConsole();
    await waitFor(() => {
      expect(screen.getByText('A1001')).toBeInTheDocument();
    });

    expect(screen.getByText('W01928')).toBeInTheDocument();
    expect(screen.getByText('W08371')).toBeInTheDocument();
    expect(screen.getAllByText(/৳৩৫,০০০/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/মি\./i).length).toBeGreaterThanOrEqual(1); // Live time left in minutes
  });

  it('opens detail drawer and displays narrative, reason codes, and local wallet graph', async () => {
    renderAnalystConsole();
    await waitFor(() => {
      expect(screen.getByText('A1001')).toBeInTheDocument();
    });

    const investigateBtn = screen.getByRole('button', { name: /তদন্ত করুন/i });
    fireEvent.click(investigateBtn);

    await waitFor(() => {
      expect(screen.getByText(/সতর্কতা বিস্তারিত #A1001/i)).toBeInTheDocument();
      expect(screen.getByText('RECIPIENT_FAN_IN_BURST')).toBeInTheDocument();
      expect(screen.getByText(/লোকাল ওয়ালেট গ্রাফ/i)).toBeInTheDocument();
      expect(screen.getByText(/W08371 \(Target\)/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/পূর্ববর্তী পদক্ষেপ ও অডিট হিস্টোরি/i)).toBeInTheDocument();
  });

  it('validates release action requiring analyst note', async () => {
    renderAnalystConsole();
    await waitFor(() => {
      expect(screen.getByText('A1001')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /তদন্ত করুন/i }));
    await waitFor(() => {
      expect(screen.getByText(/সতর্কতা বিস্তারিত #A1001/i)).toBeInTheDocument();
    });

    // Click release without note
    const releaseBtn = screen.getByRole('button', { name: /লেনদেন অবমুক্ত করুন/i });
    fireEvent.click(releaseBtn);

    await waitFor(() => {
      expect(screen.getByText(/লেনদেন অবমুক্ত করার জন্য অ্যানালিস্ট নোট উল্লেখ করা বাধ্যতামূলক/i)).toBeInTheDocument();
    });

    // Provide note and click release again
    const noteInput = screen.getByPlaceholderText(/লেনদেন অবমুক্ত করার কারণ উল্লেখ করুন/i);
    fireEvent.change(noteInput, { target: { value: 'Verified legitimate customer emergency' } });

    fireEvent.click(releaseBtn);

    await waitFor(() => {
      expect(screen.getByText(/পদক্ষেপ সফলভাবে রেকর্ড করা হয়েছে/i)).toBeInTheDocument();
    });
  });

  it('approves fraud intervention successfully', async () => {
    renderAnalystConsole();
    await waitFor(() => {
      expect(screen.getByText('A1001')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /তদন্ত করুন/i }));
    await waitFor(() => {
      expect(screen.getByText(/সতর্কতা বিস্তারিত #A1001/i)).toBeInTheDocument();
    });

    const approveBtn = screen.getByRole('button', { name: /জালিয়াতি নিশ্চিত করুন/i });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(screen.getByText(/পদক্ষেপ সফলভাবে রেকর্ড করা হয়েছে/i)).toBeInTheDocument();
    });
  });
});
