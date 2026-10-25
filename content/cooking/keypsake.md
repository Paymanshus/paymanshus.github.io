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

**typed it? keyp it.** A small macOS app that saves what you type into any text box, in any app.
For the 40-minute prompt that hit a connection error, the message that vanished when you went
back to fix one word, the search you swore you'd run after this video.

- **Typed.** One entry per text box, with the app or website, its icon and the window title.
  Only what you typed this time is kept, not text that was already there.
- **The moment it all went wrong.** As you write, keypsake keeps versions. If a box suddenly
  empties or loses most of its text, the version right before is saved, marked in amber and
  shown first.
- **Changes anyone can read.** Any version against the one before: added words highlighted,
  removed words struck through, plus a plain summary like "40 words added".
- **Copied.** Clipboard history with the source app or site.
- **keypstats.** How much you typed and when, on a heat map by hour and weekday.

## Privacy

It's a keylogger you run on purpose. History is encrypted (AES-GCM) and stays on your Mac;
nothing is sent anywhere. Password fields, password managers and concealed clipboard items are
never recorded, and typed text is deleted after 7, 30, 90 or 365 days.

## How it works

A global key monitor triggers reads of the focused text box through the Accessibility API.
Where an app does not expose its text (Google Docs, some Electron apps, terminals), the text is
rebuilt from keystrokes. A sudden large drop in length saves the version before it. Storage is
SQLite with every text field sealed by CryptoKit.
