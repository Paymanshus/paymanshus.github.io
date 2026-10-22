/**
 * Streamed terminal replies and voice end-of-call messaging.
 *
 * Source assertions, like interface-fallbacks.test.mjs (the components use the
 * `@/` alias and JSX, which bare Node can't import). They pin the behaviours
 * that would quietly regress:
 *
 *   1. the terminal asks /api/chat/stream first and still falls back to the
 *      plain /api/chat request, then to the offline keyword answers
 *   2. an `llm_unavailable` stream doesn't trigger a second, doomed request
 *   3. the voice view shows why the agent ended the call
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
const STREAM_SRC = read('lib', 'chatStream.ts');

test('terminal streams first, then plain request, then keyword fallback', () => {
  assert.match(CHAT_SRC, /const streamEndpoint = `\$\{endpoint\}\/stream`;/, 'uses /api/chat/stream');
  assert.match(CHAT_SRC, /readChatStream\(res,/);
  const plain = CHAT_SRC.indexOf('await fetch(endpoint,');
  const keyword = CHAT_SRC.lastIndexOf('keywordFallback(question)');
  assert.ok(plain !== -1 && keyword > plain, 'plain /api/chat retry, then local fallback');
});

test('llm_unavailable skips the plain retry', () => {
  assert.match(CHAT_SRC, /if \(llmUnavailable\) throw new Error\('llm_unavailable'\)/);
});

test('stream reader handles delta, done and error events', () => {
  for (const kind of ['delta', 'done', 'error']) assert.ok(STREAM_SRC.includes(kind));
  assert.match(STREAM_SRC, /indexOf\('\\n\\n'\)/, 'splits events on blank lines');
});

test('voice view explains an agent-ended call', () => {
  assert.match(VOICE_SRC, /agentAttributes\?\.\['voice\.end_reason'\]/);
  assert.match(VOICE_SRC, /'time_limit'/);
  assert.match(VOICE_SRC, /'idle'/);
});
