import type { ConvertResponse, TestMode } from './types';

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export interface ConvertInput {
  python_code: string;
  tests?: string;
  test_mode?: Exclude<TestMode, 'auto'>;
  max_attempts?: number;
}

export async function convert(input: ConvertInput): Promise<ConvertResponse> {
  const response = await fetch(`${API_BASE}/convert`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });

  const text = await response.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    // Non-JSON error payload; fall through to the status-based message.
  }

  if (!response.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((item) => (typeof item === 'object' && item && 'msg' in item ? String((item as { msg: unknown }).msg) : String(item)))
              .join('; ')
          : `Request failed with HTTP ${response.status}`;
    throw new Error(message);
  }

  return data as ConvertResponse;
}
