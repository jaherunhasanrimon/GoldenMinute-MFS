import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { I18nProvider } from '../locales/i18n';
import { CustomerDemo } from '../pages/CustomerDemo';

const renderCustomerDemo = () => {
  return render(
    <I18nProvider>
      <CustomerDemo />
    </I18nProvider>
  );
};

describe('CustomerDemo Component Tests', () => {
  beforeEach(() => {
    localStorage.clear();

    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      const urlStr = String(url);
      const method = init?.method || 'GET';

      if (urlStr.includes('/v1/demo/accounts')) {
        return Promise.resolve(new Response(JSON.stringify({
          senders: [
            { wallet_id: 'W01928', customer_id: 'C10001', name: 'Karim Ahmed', balance_bdt: 45000, persona: 'salaried', description: 'Regular salary' }
          ],
          recipients: [
            { wallet_id: 'W08371', customer_id: 'C90001', name: 'Mule W08371', balance_bdt: 3400, persona: 'mule', description: 'Fresh wallet burst' }
          ]
        }), { status: 200 }));
      }

      if (urlStr.includes('/v1/score') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}'));
        const amount = body.amount_bdt || 0;

        let action = 'allow';
        let riskScore = 0.05;
        if (amount >= 30000) {
          action = 'hold';
          riskScore = 0.95;
        } else if (amount >= 15000) {
          action = 'verify';
          riskScore = 0.75;
        } else if (amount >= 5000) {
          action = 'warn';
          riskScore = 0.45;
        }

        return Promise.resolve(new Response(JSON.stringify({
          txn_id: 'TXN-TEST-123',
          risk_score: riskScore,
          action: action,
          reason_codes: [
            { code: 'AMOUNT_UNUSUAL_FOR_SENDER', weight: 0.7 },
            { code: 'FIRST_TIME_PAIR', weight: 0.3 }
          ],
          customer_message: {
            bn: 'এই পরিমাণ আপনার সাধারণ লেনদেনের তুলনায় অনেক বেশি। পাঠানোর আগে আপনার জানা নম্বরে সরাসরি ফোন করে নিশ্চিত হয়ে নিন।',
            en: 'This amount is much larger than you usually send. Before sending, call the person on a number you already have.'
          },
          alert_id: action === 'hold' ? 'A10099' : null,
          model_version: 'm-1.0.0-full',
          policy_version: '0.1',
          latency_ms: 12.4
        }), { status: 200 }));
      }

      if (urlStr.includes('/v1/feedback') && method === 'POST') {
        return Promise.resolve(new Response(JSON.stringify({
          feedback_id: 'FB-TEST-01',
          status: 'recorded'
        }), { status: 200 }));
      }

      if (urlStr.includes('/v1/simulate/attack') && method === 'POST') {
        return Promise.resolve(new Response(JSON.stringify({
          status: 'started',
          scenario_id: 'impersonation_scam_01',
          message: 'Attack scenario replayed',
          steps: [
            { step: 1, title: 'Step 1', action: 'allow', amount_bdt: 250, description: 'Test probe transfer' },
            { step: 2, title: 'Step 2', action: 'warn', amount_bdt: 8000, description: 'Second victim' },
            { step: 3, title: 'Step 3', action: 'warn', amount_bdt: 35000, description: 'Coercive transfer' },
            { step: 4, title: 'Step 4', action: 'hold', amount_bdt: 35000, risk_score: 0.95, alert_id: 'A_ATK_01', description: 'Scoring triggered hold' },
            { step: 5, title: 'Step 5', action: 'hold', amount_bdt: 35000, risk_score: 0.95, alert_id: 'A_ATK_01', description: 'Analyst intervention' }
          ]
        }), { status: 200 }));
      }

      if (urlStr.includes('/v1/simulate/reset') && method === 'POST') {
        return Promise.resolve(new Response(JSON.stringify({
          status: 'reset_completed',
          message: 'Demo state reset'
        }), { status: 200 }));
      }

      return Promise.resolve(new Response(JSON.stringify({ status: 'ok' }), { status: 200 }));
    }));
  });

  it('renders demo accounts and send money form', async () => {
    renderCustomerDemo();
    await waitFor(() => {
      expect(screen.getByText(/Karim Ahmed/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Mule W08371/i)).toBeInTheDocument();
  });

  it('supports toggling custom recipient input', async () => {
    renderCustomerDemo();
    await waitFor(() => {
      expect(screen.getByText(/Karim Ahmed/i)).toBeInTheDocument();
    });

    const toggleBtn = screen.getByText(/নতুন নম্বর লিখুন/i);
    fireEvent.click(toggleBtn);

    const customInput = screen.getByPlaceholderText(/e\.g\. 01899123456/i);
    expect(customInput).toBeInTheDocument();
    fireEvent.change(customInput, { target: { value: '01811223344' } });
    expect(customInput).toHaveValue('01811223344');
  });

  it('submits send-money and displays hold intervention with reasons', async () => {
    renderCustomerDemo();
    await waitFor(() => {
      expect(screen.getByText(/Karim Ahmed/i)).toBeInTheDocument();
    });

    // Preset 35,000 to trigger hold
    const preset35k = screen.getByText(/৳৩৫,০০০/i);
    fireEvent.click(preset35k);

    const submitBtn = screen.getByRole('button', { name: /টাকা পাঠান/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/তদন্তের জন্য স্থগিত/i)).toBeInTheDocument();
      expect(screen.getByText('AMOUNT_UNUSUAL_FOR_SENDER')).toBeInTheDocument();
      expect(screen.getByText('A10099')).toBeInTheDocument();
    });

    // Click "This was me" feedback button
    const feedbackBtn = screen.getByText(/আমি নিজেই এই লেনদেনটি করেছি/i);
    fireEvent.click(feedbackBtn);

    await waitFor(() => {
      expect(screen.getByText(/আপনার প্রতিক্রিয়া অ্যানালিস্ট কিউ-তে পাঠানো হয়েছে/i)).toBeInTheDocument();
    });
  });

  it('submits send-money with 15k and displays verify intervention with cooling-off timer', async () => {
    renderCustomerDemo();
    await waitFor(() => {
      expect(screen.getByText(/Karim Ahmed/i)).toBeInTheDocument();
    });

    const preset15k = screen.getByText(/৳১৫,০০০/i);
    fireEvent.click(preset15k);

    const submitBtn = screen.getByRole('button', { name: /টাকা পাঠান/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/অতিরিক্ত যাচাই প্রয়োজন/i)).toBeInTheDocument();
      expect(screen.getByText(/নিরাপত্তা বিরতি/i)).toBeInTheDocument();
      expect(screen.getByText(/পরিচিত ব্যক্তির অনুমোদন নিশ্চিত করুন/i)).toBeInTheDocument();
    });

    // Click trusted contact confirmation
    const confirmBtn = screen.getByText(/পরিচিত ব্যক্তির অনুমোদন নিশ্চিত করুন/i);
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByText(/বিশ্বস্ত ব্যক্তির অনুমোদন সম্পন্ন হয়েছে/i)).toBeInTheDocument();
    });
  });

  it('runs attack simulation and renders 5 animated steps', async () => {
    renderCustomerDemo();
    await waitFor(() => {
      expect(screen.getByText(/Karim Ahmed/i)).toBeInTheDocument();
    });

    const runAttackBtn = screen.getByText(/অ্যাটাক চালান/i);
    fireEvent.click(runAttackBtn);

    await waitFor(() => {
      expect(screen.getByText(/Attack scenario replayed/i)).toBeInTheDocument();
    }, { timeout: 3000 });

    expect(screen.getByText('Illustrative scenario (synthetic)')).toBeInTheDocument();
  });
});
