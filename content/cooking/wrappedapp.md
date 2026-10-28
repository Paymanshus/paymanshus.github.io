---
title: WrappedApp
summary: Your WhatsApp chats, wrapped. Local-first, and it runs entirely in the browser.
date: 2026-10-05
status: building
stack: [React, Vite, Tailwind v4, Dexie, Transformers.js, Recharts, Ollama]
repo: https://github.com/Paymanshus/WrappedApp
thumbnail:
  src: /cooking/wrappedapp/desktop-dashboard.webp
  alt: WrappedApp dashboard showing a chat personality card, message totals and messages per month over four years.
  width: 1600
  height: 1000
media:
  - src: /cooking/wrappedapp/desktop-story-2.webp
    alt: A Rewind story card on desktop.
    width: 1600
    height: 1000
  - src: /cooking/wrappedapp/phone-story-2.webp
    alt: The same Rewind story card on a phone.
    width: 555
    height: 1200
  - src: /cooking/wrappedapp/desktop-hall-of-fame.webp
    alt: The Hall of Fame view of standout messages.
    width: 1600
    height: 1000
  - src: /cooking/wrappedapp/phone-dashboard.webp
    alt: The dashboard on a phone.
    width: 555
    height: 1200
  - src: /cooking/wrappedapp/desktop-find.webp
    alt: Search with filters for people, dates, media and time of day.
    width: 1600
    height: 1000
  - src: /cooking/wrappedapp/phone-find.webp
    alt: Search on a phone.
    width: 555
    height: 1200
---

My WhatsApp ate my old chats. After a not-so-official move from Android to iPhone, years of
messages vanished from the app, but they still showed up, weirdly, when I exported the chat.
Plenty of people online are stuck in the same glitch. Some of those chats mattered to me, so I
built a little fake-WhatsApp reader just to read them again.

Then the obvious thought: the whole chat is sitting right here, so why stop at reading it?

- **Rewind.** A tap-through story of the chat, with its own soundtrack.
- **Dashboard.** Who texts more, when you talk, streaks and signature words.
- **Reader and search.** The full chat, with filters for people, dates, media and time of day.
- **Share.** Posters and videos, ready to post.

## Ask (still cooking)

Ever tried finding someone's birthday in a chat? You search "happy birthday" and get every
birthday of everyone you've ever wished. Or you're settling a "I told you to do this" / "no you
didn't": you know it happened, you just don't remember the exact words, so search can't find
it. Ask is an agentic search for exactly that. Describe what you're after and it digs through
the chat for you. It's early, and it runs against a local model through Ollama or your own API
key.

## Privacy

There is no server. Chats, media and stats never leave your browser.
