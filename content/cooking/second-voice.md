---
title: Second Voice
summary: A typing-first speech app that talks in your own cloned voice, for people who have lost theirs.
date: 2026-10-09
status: building
stack: [Expo, React Native, expo-sqlite, Zustand, Cartesia, ElevenLabs]
---

Built for people who have lost or are losing their voice: laryngectomy, ALS, voice box damage.
You type or tap, and the phone speaks in your own cloned voice. A quick bar holds your most-used
phrases, suggestions complete from your own history, and any utterance can go out as a WhatsApp
voice note.

Every request walks a fallback chain so the phone always says something: a local cache answers
in under 300ms, then Cartesia, then ElevenLabs, then the phone's built-in voice. The switch is
silent, with no error dialogs.
