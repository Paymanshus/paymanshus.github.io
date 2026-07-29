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
