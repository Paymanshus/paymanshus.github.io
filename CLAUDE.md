@AGENTS.md

# Working rules for agents (from the owner)

## Cost
- Test and benchmark cost-effectively. Use free sources first (OpenRouter
  catalogue, endpoint stats and docs, provider docs), then the smallest set of
  real calls that answers the question: screen with 1-2 rounds, and only run
  more rounds for the few candidates left.
- Estimate paid spend before a run and report it after. Anything beyond a few
  cents needs the owner's OK first.
- Keep runtime cost down too: cache what can be cached (prompt prefixes,
  pre-rendered voice lines), no reasoning tokens on voice/terminal calls, no
  per-visitor work that isn't needed.

## Deploying and shared work
- Never deploy, push to `main`, or touch the live VM's running containers
  without the owner's explicit go-ahead. The deploy runbook is
  `deploy/oracle/README.md`.
- Other Claude sessions often work in the same checkout. Make changes in a
  separate git worktree and branch; never switch branches in the shared
  checkout. Check `git log` before editing `agent/main.py`, and leave a note in
  the shared notes folder when you take over a file another session owns.

## Measuring
- Measure from the Oracle VM (the production network), in a throwaway
  container started from the live image (`docker run --rm ... ps-agent:latest`),
  never inside the live process. Point probes at their own breaker/state files.
- Write results up in `readmes/perf/<date>/`: a README with the summary and
  decisions, one `tests/NN-*.md` per test (method, results, findings), raw
  output in `raw/`. These folders are gitignored here; save them to the
  private repo with `../vibesite2k26-private/sync.sh` (see `AGENTS.md`).

## Voice and terminal product priorities
- Voice: speed matters more than model quality. P95 latency and the first turn
  (greeting and first answer) matter most.
- Never add backoff, longer timeouts or waits a live user sits through. Prefer
  hedging, health checks and switching providers before a turn depends on them.
- The terminal can be slightly better quality than voice, but not "pro" models.
- Persona prompts live in `agent/prompts.py`. Never let a prompt or example
  state facts, plans or opinions about the owner that aren't on the resume or
  in his own writing.

## Environment quirks (owner's Windows + WSL laptop)
Cloud sessions run plain Linux and can skip the WSL notes below. Their traffic
goes through an HTTP proxy, so they most likely can't reach the VM's SSH port
(untested); HTTPS checks against `https://ps-agent.duckdns.org` work once that
host is allowed in the environment's network settings.
- The repo lives in WSL (`~/code/vibesite2k26`). Run git, node and Python
  through `wsl.exe -d ubuntu -- bash -lc '...'`; git over the UNC path fails
  with "dubious ownership".
- Use the Linux Node from `~/.nvm/versions/node/v22.*/bin`; the Windows `npx`
  comes first on the WSL PATH otherwise.
- The VM's SSH key is `~/.ssh/oracle_agent` in WSL. `docker run --env-file
  /opt/agent/agent.env` keeps inline `# comments` and quotes that compose strips;
  scripts must normalise env values before using them.
