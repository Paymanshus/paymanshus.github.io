# My views on AI coding and building

## Vibe coding is a spectrum
<!-- keywords: vibe coding ai coding ai-assisted development karpathy productivity 10x hype copilot -->
Some days the vibes are immaculate. Some days they aren't. So if vibes are a spectrum, why look at vibe coding so binarily? Between straight hostility and unwavering worship, I try to hold the middle ground: get the best out of it, and be honest about where it struggles. I've used AI coding a lot at work and on side projects, and it can genuinely 10x your development. What I don't buy is the fake 100x promise that breaks the moment you leave a demo running five hardcoded examples. I'm sure even Karpathy didn't mean to start a mini war when he coined the term. Vibe coding should be personal: tune it to your vibe. Just maybe don't go all vibes, all the time (or do, idk, I'm not your manager).

## How I work with AI coding tools
<!-- keywords: cursor claude ide readme documentation custom instructions coding agent tips workflow -->
One habit that's paid off: alongside the normal README, keep a detailed one that breaks down how every part of the app works. It's good documentation, sure, but it's even more useful for the next LLM session. Every time you spin up a new chat in whatever AI IDE you're on (which should ideally be a lot), there's a search fired off just to understand what's going on before it gets to what you actually asked. Specific code changes need specific searches, no two ways about that. But the overall understanding of how the app works can come from a ready reference. Bonus: have some custom instructions going too. And I don't treat my own prompts as gospel; I want the tool to make judgement calls.

## AI-built apps all look the same
<!-- keywords: design ui ux vibe-coded apps taste creativity figma generic designer -->
I'm not a designer, but I enjoy tastefully made design. I usually struggle and annoy the more design-oriented folks around me for it, though those back-and-forths have been great for me (not sure they'd say the same :)). Ever since AI coding has been a thing, making well-crafted apps, even vibe-coded ones, has been insanely fun, and the opportunities are genuinely endless. But every vibe-coded app looking the absolute same with minimal creativity has been a pet peeve of mine, and a cardinal sin I've never wanted to commit myself. I'm trying to get better at bridging that gap on my own, for side projects and for work.

## Picking the lightest tool
<!-- keywords: react htmx plain html simplicity over-engineering overengineering hybrid search deterministic filters -->
I don't like shoving React and TypeScript into everything. When I wanted a little app to search my IMDb watchlist by vibe, I started at React and talked myself out of it halfway through the thought: it's simple enough that plain HTML or something HTMX-like does the job. Same with the AI part. Dumping a thousand movies into an LLM's context would be a pretty bad solution. So the plan was deterministic, programmatic filters first (genres and so on, a thousand down to maybe a hundred), and only then an LLM search over the small set with short synopses. Manual plus AI hybrid. It's a personal app, so I'm fine doing the filtering myself.
