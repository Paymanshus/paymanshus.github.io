/**
 * Agent server resolution.
 *
 * The voice and terminal interfaces both talk to the Python agent server
 * (token minting for LiveKit, and the resume-grounded chat endpoint).
 *
 * `localhost` must never reach a deployed build. A production bundle that
 * falls back to http://localhost:8080 points every visitor's browser at
 * their own machine: the request always fails, and the URL shows up in
 * their devtools console and network panel. So the localhost default is
 * scoped to development only — in production an unset variable means
 * "no agent", and callers are expected to skip the network entirely
 * rather than fire a request that cannot succeed.
 *
 * NEXT_PUBLIC_* values are inlined at build time, so this resolves once
 * during `next build` and is constant at runtime.
 */

const RAW_AGENT_URL = (process.env.NEXT_PUBLIC_AGENT_URL ?? '').trim();

const DEV_AGENT_URL = 'http://localhost:8080';

/**
 * Base URL for the agent server, or '' when none is configured.
 * Trailing slashes are stripped so callers can append '/api/...' safely.
 */
export const AGENT_SERVER_URL: string = (
  RAW_AGENT_URL || (process.env.NODE_ENV === 'development' ? DEV_AGENT_URL : '')
).replace(/\/+$/, '');

/**
 * True when a backend is configured and worth calling. When false, the UI
 * should present its offline/resting affordance without touching the
 * network — no failed fetch, no console noise.
 */
export const isAgentConfigured: boolean = AGENT_SERVER_URL !== '';

/** Build an absolute agent endpoint URL, or null when no agent is configured. */
export function agentEndpoint(path: string): string | null {
  if (!isAgentConfigured) return null;
  return `${AGENT_SERVER_URL}${path.startsWith('/') ? path : `/${path}`}`;
}

/**
 * Cheap reachability probe used before flows with an expensive or
 * irreversible first step (e.g. prompting for microphone access).
 * Resolves false rather than throwing, so callers can branch on it.
 */
export async function isAgentReachable(timeoutMs = 3000): Promise<boolean> {
  const url = agentEndpoint('/api/health');
  if (!url) return false;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { method: 'GET', signal: controller.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Why voice can't take a call right now. The first four come from the agent
 * server (/api/voice/status, or a refused /api/token); `no_show` is decided in
 * the browser when a token was granted but the agent never joined the room.
 */
export type VoiceUnavailableReason =
  | 'busy'
  | 'daily_limit'
  | 'monthly_limit'
  | 'disabled'
  | 'no_show';

export interface VoiceStatus {
  available: boolean;
  reason: 'ok' | VoiceUnavailableReason;
  active?: number;
  cap?: number;
  retry_after_s?: number;
  /** ISO-8601 UTC, when the server knows when voice is back. */
  back_at?: string;
}

/**
 * Voice availability, or null when the server can't be reached (which callers
 * treat as the "resting" state). Doubles as the reachability probe.
 */
export async function fetchVoiceStatus(timeoutMs = 3000): Promise<VoiceStatus | null> {
  const url = agentEndpoint('/api/voice/status');
  if (!url) return null;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { method: 'GET', signal: controller.signal });
    if (!res.ok) return null;
    return (await res.json()) as VoiceStatus;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/** "Tell me when AI me is back." Never throws. */
export async function joinVoiceWaitlist(
  email: string,
  reason: VoiceUnavailableReason
): Promise<'ok' | 'invalid' | 'error'> {
  const url = agentEndpoint('/api/voice/notify');
  if (!url) return 'error';
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, reason }),
    });
    if (res.ok) return 'ok';
    return res.status === 400 ? 'invalid' : 'error';
  } catch {
    return 'error';
  }
}
