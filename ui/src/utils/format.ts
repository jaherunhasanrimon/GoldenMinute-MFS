/**
 * BDT Currency and Bengali Digits Formatting Utility
 * Formats numbers, currencies, and dates in English or Bengali script.
 */

const BENGALI_DIGITS = ['০', '১', '২', '৩', '৪', '৫', '৬', '৭', '৮', '৯'];

export function toBengaliDigits(numStr: string | number): string {
  return String(numStr).replace(/\d/g, (d) => BENGALI_DIGITS[parseInt(d, 10)] || d);
}

export function formatBDT(amount: number, lang: 'en' | 'bn' = 'en'): string {
  const formatted = amount.toLocaleString('en-IN', {
    maximumFractionDigits: 2,
    minimumFractionDigits: amount % 1 === 0 ? 0 : 2,
  });

  if (lang === 'bn') {
    return `৳${toBengaliDigits(formatted)}`;
  }
  return `৳${formatted}`;
}

export function formatSecondsCountdown(seconds: number, lang: 'en' | 'bn' = 'en'): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  const timeStr = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  return lang === 'bn' ? toBengaliDigits(timeStr) : timeStr;
}

export function formatTimeLeft(deadlineTsStr: string, lang: 'en' | 'bn' = 'en'): string {
  const deadline = new Date(deadlineTsStr).getTime();
  const now = Date.now();
  const diffMs = deadline - now;

  if (diffMs <= 0) {
    return lang === 'bn' ? 'সময় সমাপ্ত (Late)' : 'Expired (Late)';
  }

  const diffMins = Math.ceil(diffMs / 60000);
  if (lang === 'bn') {
    return `${toBengaliDigits(diffMins)} মি.`;
  }
  return `${diffMins}m`;
}
