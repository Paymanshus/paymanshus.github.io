# My views on AI and agents

## Do you really need an AI agent?
<!-- keywords: agents agentic workflows autonomy agent vs workflow llm agents hype overhyped -->
Every other person I talk to seems to be building an AI agent, has built one, or has struggled with one. So I like stepping back and asking: are you sure you need one? I don't look at agents as a yes or no thing. It's a spectrum of how agent-y a solution is. Workflows get shunned because agents seem cooler, but more often than not a workflow is the more effective way to add a lil AI spice. I've seen the same problem attacked at every level of autonomy, from I-don't-really-trust-these-AI-bots all the way to give-the-problem-to-our-LLM-gods-and-pray. One size never fits all. LLMs are way smarter than they were a year ago, and zero to demo is easy now, but real products still need solid foundations, not buzzwords.

## My rule of thumb for agents
<!-- keywords: agentic restriction constraints inputs outputs funnel heuristic agentic patterns -->
Think of an agentic solution like a funnel. You have a tradeoff. Either you make the inputs really diverse and account for lots of variable things, but keep the output restricted. Or you keep the inputs somewhat restricted and let the LLM go crazy with the output. At least one point of restriction is where an agentic solution can really shine. If you have more than one restriction point, you're leaning towards a workflow, which is often fine. If you have less than one, it's pure creativity, built on magic and hopes and prayers.

## The model is the easy part
<!-- keywords: production ai enterprise ai magic data foundation harness reality check hype -->
The model is the easy part. The hard, ongoing, domain-specific work is feeding it the right context and proving it's right. Data is the foundation. AI-ready data goes on top of that. Then come use-case-specific requirements and context setting. And even after all that, the work isn't done: you need validation on the fly, and evals to check how well you "really" did. AI isn't magic. I'm genuinely hopeful about what AI can do, but I want people to be careful too, and to separate what they think can work from what the on-ground reality ends up being.

## Context is precision work
<!-- keywords: context engineering context window rag retrieval lost in the middle long context token cost -->
Getting the right context to a model at the right time is precision work, and it needs to be done carefully, not in a shotgun pattern, once your data foundations are in place. What seems easy and straightforward, like plain RAG, often isn't enough, and you end up needing more that you didn't think of at the start. Big context windows are also a trap: having a million tokens of space doesn't mean you should use it. Performance dips for stuff buried in the middle of a long context, and you pay more for it too. Ever since LLMs became a thing I've started thinking about everything in context windows. Forgot something in the kitchen? It escaped my context window.

## Evals and trust
<!-- keywords: evals evaluation evaluate evaluating validation llm as a judge trust hallucination hallucinations confidently wrong deterministic testing -->
AI is confidently wrong a lot, and confidence isn't correctness. Something can look great in a demo and still not be good consistently. So for me, validation is what builds trust. You can't make an LLM deterministic, but you can keep raising the probability that it succeeds until it gets close to deterministic in practice. One approach I like is making models fight it out: different models or personas checking each other. Battle testing an LLM system is different and harder than testing normal software, but having something in place beats overanalysing it.

## Sycophancy, and why I like an AI that pushes back
<!-- keywords: sycophancy sycophantic bullshit bench benchmarks absolutely right model behaviour thinking models -->
The Bullshit Bench is hands down the best way I've seen to check sycophancy as a benchmark, and some of the questions are hilarious. It makes sense that a lot of otherwise useful models struggle with it: newer models, especially thinking models, are trained to accomplish the task no matter what. My own use checks out with this. Nothing makes me happier than a sassy Claude calling out my half baked ideas and straight up refusing to make changes the way I suggested (and being right about it, obviously). If I see another "You're absolutely right" though, I'm pulling that GPU plug hard.

## AI in 2025, and why the reactions fascinate me
<!-- keywords: worldview future of ai jobs fear society history internet public sentiment regulation replace -->
Working in AI right now feels like a privilege, honestly the most empowering thing I've been part of. Sci-fi I grew up watching is materialising. But what's interested me most lately isn't the leaps, it's how people react. Job insecurity, not knowing how to regulate it, general uncertainty. For everyone fully bullish there's someone worried, and rightly so. People who lived through Y2K and the birth of the internet keep pointing out it's happened before: computers went from giant government machines to something on your desk. Power and fear always go hand in hand. What's new is that everyone can broadcast how they feel in real time, so public sentiment is visible like never before, and more volatile.
