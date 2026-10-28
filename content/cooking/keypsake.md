---
title: keypsake
summary: Everything you type, kept. A macOS app that saves typed text in any app, plus clipboard history.
date: 2026-10-24
status: building
stack: [Swift, SwiftUI, AppKit, Accessibility API, SQLite, CryptoKit]
repo: https://github.com/Paymanshus/keypsake
thumbnail:
  src: /cooking/keypsake/typed.webp
  alt: The Typed tab, showing an email draft that was cleared, with the version before the loss marked in amber.
  width: 1600
  height: 1037
video:
  src: /cooking/keypsake/keypsake.mp4
  poster: /cooking/keypsake/poster.webp
  alt: A long prompt in Claude Code dies to a connection error, then keypsake brings it back.
  width: 1280
  height: 720
media:
  - src: /cooking/keypsake/typed.webp
    alt: "Typed: one entry per text box, with versions and a Changes view of what was added or removed."
    width: 1600
    height: 1037
  - src: /cooking/keypsake/copied.webp
    alt: "Copied: clipboard history with the source app or site, and ⌘1–9 to copy one back."
    width: 1600
    height: 1037
  - src: /cooking/keypsake/stats.webp
    alt: "keypstats: words typed this week, and a heat map of when you were most key-krazy."
    width: 1600
    height: 1037
  - src: /cooking/keypsake/settings.webp
    alt: Settings, including how long typed text is kept.
    width: 819
    height: 1200
---

**typed it? keyp it.**

Most work is a prompt now. Typing used to be short and surgical; now it's half an hour of
paragraphs for a model, copied and pasted across five apps, with a clipboard that quietly eats
whatever was there before. Then the connection drops, the page reloads, or one paste lands on top
of the thing you spent 40 minutes writing. Gone.

I got sick of losing my prompts, so I built the thing that keeps them. keypsake saves what you
type into any text box, in any app, plus your clipboard history. It's on Mac now and meant for
Windows too, because nobody on any OS deserves to lose their words.

- **Typed.** One entry per text box, with the app or website, its icon and the window title.
  It keeps just what you typed this time.
- **The moment it all went wrong.** As you write, keypsake keeps versions. If a box suddenly
  empties or loses most of its text, the version right before is saved, marked in amber and
  shown first.
- **Changes anyone can read.** Any version against the one before: added words highlighted,
  removed words struck through, plus a plain summary like "40 words added".
- **Copied.** Clipboard history with the source app or site, so a careless paste can't take
  anything with it.
- **keypstats.** Even if you never lose a word, it's a kick to see how much you type, where, and
  when you were most key-krazy, on a heat map by hour and weekday.

I use it every day, and it has already saved me more retyping than I'd like to admit.

## Privacy

It's a keylogger you run on purpose, so trust came first. History is encrypted (AES-GCM) and
stays on your Mac; nothing is sent anywhere. Password fields, password managers and concealed
clipboard items are never recorded, and typed text is deleted after 7, 30, 90 or 365 days.

Don't take my word for it. Point your own coding agent at the repo and ask it: is this safe, and
does my text go anywhere?
