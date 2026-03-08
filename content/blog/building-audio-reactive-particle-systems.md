---
title: "Building Audio-Reactive Particle Systems"
excerpt: "Translating voice into visual feedback with Canvas rendering and the Web Audio API."
date: "2026-01-28"
tags:
  - audio
  - canvas
  - frontend
---

Voice interfaces are invisible by default. When you speak to an AI, you are talking into a black box. Good visual feedback makes that interaction feel less abstract and more alive.

Audio-reactive particle systems solve that problem elegantly. By tracking amplitude and frequency in real time, a canvas scene can respond to speech with motion that feels synchronized rather than decorative.

In the Voice Resume mode here, the particle field stays structured. Squares and crosses replace soft circles so the visuals match the more austere design language. When the system speaks, the field pushes outward with a red bleed from the center. When the user speaks, the movement tightens inward.

The technical challenge is performance. Thousands of particles at 60fps require discipline. `requestAnimationFrame` drives the loop, state changes inside the drawing context stay minimal, and the Web Audio API provides the live signal through an `AnalyserNode`.

The effect is more than eye candy. It gives the conversation a body. The interface feels responsive because it is visibly reacting to the exchange as it happens.
