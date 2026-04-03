Tech Recommendations
Next.js for the full site — SSR matters for the blog (SEO). Framer Motion for all animations. The voice interface will need a real-time audio layer; LiveKit is the recommended infrastructure (can plug this in later, mock for first build). The terminal/chat and voice interfaces both call an LLM backend with resume content pre-loaded as context (create mock, will update later).

Establish a Color System from the attached pages you see before starting. There should be the following colors:
Dark Mode (Primary)

Background
Surface
Border / structural lines
Text primary
Text secondary
Brand red
Glow layer (shadows/halos only, never fill)
The Tron Glow

Typography
Do not use: Inter, Plus Jakarta Sans, Outfit, DM Sans, Manrope, Figtree, Sora, Poppins, Nunito, General Sans, Cabinet Grotesk, or any system default.

Layout Principles
12-column grid, generous gutters, 1280px max-width, centered. All spacing in multiples of 8px. Default alignment is left — centering is reserved for singular moments of emphasis. Hierarchy is established through scale and position, not background color or decoration.

Animations
All animations must run at 60fps or be removed. No exceptions.

Dark mode is the primary experience; light mode is a first-class alternate, not an afterthought.
The design language is called Austere Neon — minimal, architectural, governed by negative space — with a single accent color (red) that appears purposefully and sparingly. When in doubt about whether to add red somewhere: don't.