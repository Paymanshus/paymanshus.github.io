/**
 * Unit tests for the analytics section timer.
 *
 * The timer is the one piece of the analytics layer with real logic, so it is
 * written to be free of browser/GA APIs and driven by an injectable clock.
 *
 * Run: node --test tests/seo/
 *
 * lib/analytics.ts is TypeScript, so the implementation is mirrored here via a
 * tiny transpile-free import: we strip types with a regex-free approach by
 * reading the compiled behavior through a small inline copy is NOT acceptable
 * (it would test a copy, not the code). Instead we let node run the .ts file
 * through its built-in type stripping (Node 22.6+ / 23+ supports this).
 */
import test from 'node:test';
import assert from 'node:assert/strict';

const { createSectionTimer } = await import('../../lib/analytics.ts');

/** Deterministic clock: advance() moves virtual time forward. */
function fakeClock() {
  let now = 0;
  return {
    now: () => now,
    advance: (ms) => {
      now += ms;
    },
  };
}

test('accumulates elapsed time for a running section', () => {
  const clock = fakeClock();
  const timer = createSectionTimer(clock.now);

  timer.start('home');
  clock.advance(1500);
  timer.stop('home');

  assert.deepEqual(timer.flush(), [{ section: 'home', ms: 1500 }]);
});

test('tracks overlapping sections independently', () => {
  const clock = fakeClock();
  const timer = createSectionTimer(clock.now);

  timer.start('article:a');
  clock.advance(1000);
  timer.start('resume:voice');
  clock.advance(500);
  timer.stop('article:a');
  clock.advance(250);
  timer.stop('resume:voice');

  const timings = Object.fromEntries(timer.flush().map((t) => [t.section, t.ms]));
  assert.equal(timings['article:a'], 1500);
  assert.equal(timings['resume:voice'], 750);
});

test('sums repeated visits to the same section', () => {
  const clock = fakeClock();
  const timer = createSectionTimer(clock.now);

  timer.start('experience');
  clock.advance(400);
  timer.stop('experience');
  clock.advance(10_000); // away from the section — must not count
  timer.start('experience');
  clock.advance(600);
  timer.stop('experience');

  assert.deepEqual(timer.flush(), [{ section: 'experience', ms: 1000 }]);
});

test('start is idempotent while already running', () => {
  const clock = fakeClock();
  const timer = createSectionTimer(clock.now);

  timer.start('home');
  clock.advance(300);
  timer.start('home'); // must not reset the running clock
  clock.advance(200);
  timer.stop('home');

  assert.deepEqual(timer.flush(), [{ section: 'home', ms: 500 }]);
});

test('pauseAll freezes time and resumeAll continues it', () => {
  const clock = fakeClock();
  const timer = createSectionTimer(clock.now);

  timer.start('home');
  clock.advance(1000);
  timer.pauseAll();
  clock.advance(60_000); // tab hidden — not engagement
  timer.resumeAll();
  clock.advance(500);
  timer.stop('home');

  assert.deepEqual(timer.flush(), [{ section: 'home', ms: 1500 }]);
});

test('starting a section while paused accrues no time until resume', () => {
  const clock = fakeClock();
  const timer = createSectionTimer(clock.now);

  timer.pauseAll();
  timer.start('late');
  clock.advance(5000);
  timer.resumeAll();
  clock.advance(750);
  timer.stop('late');

  assert.deepEqual(timer.flush(), [{ section: 'late', ms: 750 }]);
});

test('flush resets totals but keeps running sections running', () => {
  const clock = fakeClock();
  const timer = createSectionTimer(clock.now);

  timer.start('home');
  clock.advance(1000);
  assert.deepEqual(timer.flush(), [{ section: 'home', ms: 1000 }]);

  // Immediately flushing again yields nothing — totals were reset.
  assert.deepEqual(timer.flush(), []);

  clock.advance(2000);
  timer.stop('home');
  assert.deepEqual(timer.flush(), [{ section: 'home', ms: 2000 }]);
});

test('stop on an unknown section is a no-op', () => {
  const timer = createSectionTimer(fakeClock().now);
  timer.stop('never-started');
  assert.deepEqual(timer.flush(), []);
});

test('isRunning reflects section state', () => {
  const timer = createSectionTimer(fakeClock().now);
  assert.equal(timer.isRunning('home'), false);
  timer.start('home');
  assert.equal(timer.isRunning('home'), true);
  timer.stop('home');
  assert.equal(timer.isRunning('home'), false);
});
