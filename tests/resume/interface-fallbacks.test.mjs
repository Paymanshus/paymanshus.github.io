/**
 * Tests for the offline/resting behaviour of the resume interfaces.
 *
 * Like tests/blog, these assert against the TSX source rather than importing
 * the components: they use the `@/` path alias and JSX, neither of which bare
 * Node resolves. What's covered here are the three regressions that shipped to
 * production and were only caught by manually driving the live site:
 *
 *   1. localhost leaking into a deployed bundle
 *   2. keyword fallbacks missing plural phrasings ("what are your skills")
 *   3. the mic permission prompt firing before the agent availability check
 *
 * Run: npm run test:unit
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), 'utf8');

const CHAT_SRC = read('components', 'resume', 'ChatResume.tsx');
const VOICE_SRC = read('components', 'resume', 'VoiceResume.tsx');
const AGENT_SRC = read('lib', 'agent.ts');

// ─── 1. localhost must not be reachable from a production bundle ──────

test('lib/agent.ts is the only client module naming localhost', () => {
  for (const [name, src] of [
    ['ChatResume.tsx', CHAT_SRC],
    ['VoiceResume.tsx', VOICE_SRC],
  ]) {
    assert.ok(
      !/localhost/i.test(src),
      `${name} must not reference localhost directly — go through lib/agent.ts`
    );
  }
});

test('the localhost default is gated behind NODE_ENV === development', () => {
  const devLine = AGENT_SRC.match(/^.*NODE_ENV.*$/m);
  assert.ok(devLine, 'lib/agent.ts should branch on NODE_ENV');
  assert.match(
    devLine[0],
    /development/,
    'the localhost fallback must apply only in development'
  );
  // The production branch must resolve to an empty string, not a URL.
  assert.match(
    AGENT_SRC,
    /development'\s*\?\s*DEV_AGENT_URL\s*:\s*''/,
    'production must resolve to an empty agent URL'
  );
});

test('callers can detect "no agent" without making a request', () => {
  assert.match(AGENT_SRC, /export const isAgentConfigured/);
  assert.match(AGENT_SRC, /export function agentEndpoint/);
  // agentEndpoint returns null rather than a relative path, so a caller that
  // forgets to check still cannot accidentally fetch.
  assert.match(AGENT_SRC, /if \(!isAgentConfigured\) return null;/);
});

test('the terminal skips the network entirely when no agent is configured', () => {
  const askLlm = CHAT_SRC.slice(CHAT_SRC.indexOf('const askLlm'));
  const guardIdx = askLlm.indexOf('if (!endpoint)');
  const fetchIdx = askLlm.indexOf('await fetch(');
  assert.ok(guardIdx > -1, 'askLlm should guard on a null endpoint');
  assert.ok(fetchIdx > -1, 'askLlm should still fetch when configured');
  assert.ok(
    guardIdx < fetchIdx,
    'the no-endpoint guard must come before the fetch'
  );
});

// ─── 2. Keyword fallbacks handle real phrasings ───────────────────────

/** Pull the live regex/category pairs straight out of the component source. */
function parseKeywordFallbacks() {
  const block = CHAT_SRC.slice(
    CHAT_SRC.indexOf('const KEYWORD_FALLBACKS'),
    CHAT_SRC.indexOf('function keywordFallback')
  );
  const pairs = [...block.matchAll(/\[\s*(\/.+?\/i)\s*,\s*'(\w+)'\s*,?\s*\]/gs)];
  assert.ok(pairs.length >= 5, 'expected at least 5 keyword fallback rules');
  return pairs.map(([, pattern, category]) => {
    const body = pattern.slice(1, pattern.lastIndexOf('/'));
    return { regex: new RegExp(body, 'i'), category };
  });
}

/** Mirrors keywordFallback(): first matching rule wins. */
function categorise(query) {
  for (const { regex, category } of parseKeywordFallbacks()) {
    if (regex.test(query)) return category;
  }
  return null;
}

const PHRASINGS = [
  // The exact question that regressed — plural of a stem with a trailing \b.
  ['what are your skills', 'skills'],
  ['what is your skill', 'skills'],
  ['tell me about your stack', 'skills'],
  ['which frameworks do you use', 'skills'],
  ['what companies have you worked at', 'experience'],
  ['tell me about your work experience', 'experience'],
  ['what is your current role', 'experience'],
  ['where did you study', 'education'],
  ['what are your degrees', 'education'],
  ['how do i contact you', 'contact'],
  ['can i reach you on linkedin', 'contact'],
  ['who are you', 'about'],
];

for (const [query, expected] of PHRASINGS) {
  test(`keyword fallback: "${query}" → ${expected}`, () => {
    assert.equal(categorise(query), expected);
  });
}

test('plural stems are not broken by a trailing word boundary', () => {
  // Regression guard: /\bskill\b/ silently fails on "skills". Any rule whose
  // stem pluralises must not close with \b.
  const offenders = parseKeywordFallbacks().filter(({ regex }) =>
    /\\b(skill|company|degree|tool|language|framework|role)\\b/.test(regex.source)
  );
  assert.deepEqual(
    offenders.map((o) => o.category),
    [],
    'these stems pluralise and must not be wrapped in a trailing \\b'
  );
});

// ─── 3. Agent availability is checked before the mic prompt ───────────

test('LLM fallback is a mark next to listening, not a full banner', () => {
  assert.equal(
    /model rate-limited — running on fallback model/.test(VOICE_SRC),
    false,
    'the greeting-turn failover must not show a full-width rate-limit banner'
  );
  assert.match(VOICE_SRC, /showFallbackMark/);
  assert.match(VOICE_SRC, /fallback model/);
  assert.match(
    VOICE_SRC,
    /voice output unavailable/,
    'TTS-down still needs the banner — output is actually gone'
  );
});

test('handleStart checks agent availability before touching the microphone', () => {
  const start = VOICE_SRC.slice(
    VOICE_SRC.indexOf('const handleStart'),
    VOICE_SRC.indexOf('switch (connState)')
  );
  const configuredIdx = start.indexOf('isAgentConfigured');
  const reachableIdx = start.indexOf('isAgentReachable');
  const micIdx = start.indexOf('isMicAlreadyGranted');

  assert.ok(configuredIdx > -1, 'handleStart should check isAgentConfigured');
  assert.ok(reachableIdx > -1, 'handleStart should probe isAgentReachable');
  assert.ok(micIdx > -1, 'handleStart should still gate on mic permission');
  assert.ok(
    configuredIdx < micIdx && reachableIdx < micIdx,
    'both availability checks must run BEFORE any microphone access'
  );
});

test('voice exposes a resting state that is not an error state', () => {
  assert.match(VOICE_SRC, /'resting'/, 'ConnectionState should include resting');
  assert.match(VOICE_SRC, /function RestingView/);
  assert.match(VOICE_SRC, /case 'resting':/);
  // The resting copy should invite the visitor back, not report a failure.
  assert.match(VOICE_SRC, /Agent Resting/i);
  assert.match(VOICE_SRC, /come back later/i);
});

test('resting has its own particle accent, distinct from the live red', () => {
  const accents = VOICE_SRC.slice(
    VOICE_SRC.indexOf('const ACCENTS'),
    VOICE_SRC.indexOf('const ACCENT_INTENSITY')
  );
  assert.match(accents, /resting:\s*\[/, 'resting needs an ACCENTS entry');
  assert.ok(
    !/resting:\s*\[255,\s*42,\s*42\]/.test(accents),
    'resting must not reuse the brand red reserved for live states'
  );
  assert.match(VOICE_SRC, /state === 'resting'/, 'resting needs its own motion');
});

// ─── PDF viewer has a visible fallback ────────────────────────────────

test('the PDF tab always shows an escape hatch, not a blank frame', () => {
  const pdf = read('components', 'resume', 'PdfResume.tsx');
  assert.ok(
    !/loading="lazy"/.test(pdf),
    'the PDF iframe must not lazy-load: it sits below the fold and stayed blank'
  );
  assert.match(pdf, /Inline preview unavailable/);
  assert.match(pdf, /Open the resume PDF/);
});
