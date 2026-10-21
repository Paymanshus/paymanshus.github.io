'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useVoiceAssistant,
  useLocalParticipant,
  useTranscriptions,
} from '@livekit/components-react';
import type { TrackReference } from '@livekit/components-react';
import type { TrackPublication } from 'livekit-client';
import { trackEvent } from '@/lib/analytics';

import {
  agentEndpoint,
  fetchVoiceStatus,
  isAgentConfigured,
  joinVoiceWaitlist,
  type VoiceUnavailableReason,
} from '@/lib/agent';

// localStorage flag set after the first successful mic grant. The Permissions
// API is the source of truth where supported; this flag covers browsers where
// permissions.query({name:'microphone'}) throws (e.g. Firefox, older Safari).
const MIC_GRANTED_KEY = 'ps-voice-mic-granted';

// A granted token whose agent hasn't joined by now is treated as unavailable
// (LiveKit full or the worker down) instead of "summoning" forever.
const AGENT_JOIN_TIMEOUT_MS = 20_000;

async function isMicAlreadyGranted(): Promise<boolean> {
  try {
    const status = await navigator.permissions.query({
      name: 'microphone' as PermissionName,
    });
    if (status.state === 'granted') return true;
    if (status.state === 'denied') return false;
    // 'prompt' — the browser will ask again; only skip our modal if the
    // user has been through it before on this device.
    return false;
  } catch {
    return localStorage.getItem(MIC_GRANTED_KEY) === '1';
  }
}

// ─── Visual state ────────────────────────────────────────────────────
// 'user'     → visitor is speaking  → particles contract, RED accent
// 'system'   → agent is speaking    → particles expand,   GREEN accent
// 'thinking' → agent is processing  → slow inward spiral, dim accent
// 'idle'     → connected, resting   → gentle drift
// 'resting'  → agent offline        → half-speed drift, cold slate accent

type VoiceState = 'idle' | 'user' | 'system' | 'thinking' | 'resting';

type RGB = [number, number, number];

const ACCENTS: Record<VoiceState, RGB> = {
  user: [255, 42, 42], // brand red — recording
  system: [34, 197, 94], // green — agent responding
  thinking: [255, 180, 60], // warm amber — processing
  idle: [255, 42, 42], // dim red heartbeat at rest
  // Cold slate, deliberately outside the site's red/green vocabulary. Red
  // reads as "live" everywhere else here, so an offline agent must not wear
  // it — the field should look dormant, not broken.
  resting: [96, 122, 148],
};

// Idle runs the accent at low intensity so red stays scarce until it matters
const ACCENT_INTENSITY: Record<VoiceState, number> = {
  user: 1,
  system: 1,
  thinking: 0.55,
  idle: 0.4,
  resting: 0.28, // dimmest of all states — present, clearly not listening
};

// Rotating "thinking" verbs, Claude Code register — quirky but not cartoony.
// Precomputed: picking one is free at runtime.
const THINKING_WORDS = [
  'Pondering',
  'Rummaging',
  'Recollecting',
  'Cross-referencing',
  'Connecting dots',
  'Sifting',
  'Mulling it over',
  'Piecing it together',
  'Consulting the archives',
  'Retracing steps',
  'Leafing through',
  'Jogging my memory',
];

function mapAgentState(agentState: string | undefined): VoiceState {
  switch (agentState) {
    case 'speaking':
      return 'system';
    case 'listening':
      return 'user';
    case 'thinking':
      return 'thinking';
    default:
      return 'idle';
  }
}

// ─── Particle system ─────────────────────────────────────────────────

class Particle {
  x = 0;
  y = 0;
  size = 0;
  type: 'square' | 'cross' = 'square';
  opacity = 0;
  vx = 0;
  vy = 0;
  baseDist = 0;
  angle = 0;
  color = '';

  constructor(private canvas: HTMLCanvasElement) {
    this.reset();
  }

  reset() {
    const centerX = this.canvas.width / 2;
    const centerY = this.canvas.height / 2;

    this.angle = Math.random() * Math.PI * 2;
    this.baseDist =
      Math.pow(Math.random(), 2.5) *
      Math.min(this.canvas.width, this.canvas.height) *
      0.8;

    this.x = centerX + Math.cos(this.angle) * this.baseDist;
    this.y = centerY + Math.sin(this.angle) * this.baseDist;

    this.size = Math.random() * 3 + 1;
    this.type = Math.random() > 0.8 ? 'cross' : 'square';

    this.vx = (Math.random() - 0.5) * 0.2;
    this.vy = (Math.random() - 0.5) * 0.2;
  }

  updateColorAndOpacity(centerX: number, centerY: number, accent: RGB, intensity: number) {
    const dist = Math.sqrt((this.x - centerX) ** 2 + (this.y - centerY) ** 2);
    if (dist < 60) {
      const [r, g, b] = accent;
      this.color = `rgb(${r | 0}, ${g | 0}, ${b | 0})`;
      this.opacity = intensity;
    } else if (dist < 180) {
      this.color = '#ffffff';
      this.opacity = Math.max(0.1, 1 - dist / 450);
    } else {
      this.color = '#e2e2e2';
      this.opacity = Math.max(0, 0.6 - dist / 600);
    }
  }

  update(state: VoiceState, amplitude: number, accent: RGB, intensity: number) {
    const centerX = this.canvas.width / 2;
    const centerY = this.canvas.height / 2;

    if (state === 'system') {
      // Agent speaking — expand proportional to amplitude
      const expandSpeed = 0.4 + amplitude * 2.6;
      this.x += Math.cos(this.angle) * expandSpeed;
      this.y += Math.sin(this.angle) * expandSpeed;
      const dist = Math.sqrt((this.x - centerX) ** 2 + (this.y - centerY) ** 2);
      if (dist < 100) {
        // Center burst on loud passages
        this.x += Math.cos(this.angle) * amplitude * 1.5;
        this.y += Math.sin(this.angle) * amplitude * 1.5;
      }
    } else if (state === 'user') {
      // Visitor speaking — contract proportional to amplitude
      const contractSpeed = 0.005 + amplitude * 0.025;
      this.x += (centerX - this.x) * contractSpeed;
      this.y += (centerY - this.y) * contractSpeed;
    } else if (state === 'thinking') {
      // Slow inward spiral while processing
      const dx = centerX - this.x;
      const dy = centerY - this.y;
      this.x += dx * 0.004 - dy * 0.006;
      this.y += dy * 0.004 + dx * 0.006;
    } else if (state === 'resting') {
      // Agent offline — same drift as idle at roughly a third speed. Motion
      // continues (the field should still feel alive, not frozen) but slowly
      // enough to read as dormant rather than waiting for input.
      this.x += this.vx * 0.35;
      this.y += this.vy * 0.35;
    } else {
      const driftScale = 1 + amplitude * 0.5;
      this.x += this.vx * driftScale;
      this.y += this.vy * driftScale;
    }

    this.updateColorAndOpacity(centerX, centerY, accent, intensity);

    const resetThreshold = 0.998 - amplitude * 0.003;
    if (Math.random() > resetThreshold) this.reset();
  }

  draw(ctx: CanvasRenderingContext2D) {
    ctx.globalAlpha = this.opacity;
    ctx.fillStyle = this.color;
    ctx.strokeStyle = this.color;
    ctx.lineWidth = 1;

    if (this.type === 'square') {
      ctx.fillRect(this.x, this.y, this.size, this.size);
    } else {
      ctx.beginPath();
      ctx.moveTo(this.x - this.size / 2, this.y);
      ctx.lineTo(this.x + this.size / 2, this.y);
      ctx.moveTo(this.x, this.y - this.size / 2);
      ctx.lineTo(this.x, this.y + this.size / 2);
      ctx.stroke();
    }
  }
}

// ─── Web Audio amplitude analysis ────────────────────────────────────

function useTrackAmplitude(mediaStreamTrack: MediaStreamTrack | undefined) {
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  const contextRef = useRef<AudioContext | null>(null);

  useEffect(() => {
    if (!mediaStreamTrack) {
      analyserRef.current = null;
      return;
    }

    const ctx = contextRef.current ?? new AudioContext();
    contextRef.current = ctx;
    if (ctx.state === 'suspended') void ctx.resume();

    const stream = new MediaStream([mediaStreamTrack]);
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.8;
    source.connect(analyser);
    // Never connect to destination — RoomAudioRenderer owns playback

    analyserRef.current = analyser;
    dataRef.current = new Uint8Array(new ArrayBuffer(analyser.frequencyBinCount));

    return () => {
      source.disconnect();
      analyserRef.current = null;
    };
  }, [mediaStreamTrack]);

  useEffect(() => {
    return () => {
      void contextRef.current?.close();
      contextRef.current = null;
    };
  }, []);

  const read = useCallback((): number => {
    const analyser = analyserRef.current;
    const data = dataRef.current;
    if (!analyser || !data) return 0;
    analyser.getByteFrequencyData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i];
    return sum / (data.length * 255);
  }, []);

  return read;
}

// ─── Particle field canvas ───────────────────────────────────────────

function ParticleField({
  voiceState,
  readAgentAmplitude,
  readUserAmplitude,
}: {
  voiceState: VoiceState;
  readAgentAmplitude: () => number;
  readUserAmplitude: () => number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef<VoiceState>(voiceState);
  const readAgentRef = useRef(readAgentAmplitude);
  const readUserRef = useRef(readUserAmplitude);

  useEffect(() => {
    stateRef.current = voiceState;
    readAgentRef.current = readAgentAmplitude;
    readUserRef.current = readUserAmplitude;
  }, [voiceState, readAgentAmplitude, readUserAmplitude]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let particles: Particle[] = [];
    const particleCount = 1800;

    const resizeCanvas = () => {
      if (containerRef.current) {
        canvas.width = containerRef.current.clientWidth;
        canvas.height = containerRef.current.clientHeight;
      }
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    for (let i = 0; i < particleCount; i++) {
      particles.push(new Particle(canvas));
    }

    let smoothAmp = 0;
    // Crossfaded accent color so red↔green transitions are gradual
    const accent: RGB = [...ACCENTS.idle] as RGB;
    let accentIntensity = ACCENT_INTENSITY.idle;

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      const state = stateRef.current;

      // Amplitude source depends on who is talking
      let amplitude = 0;
      if (state === 'system') amplitude = readAgentRef.current();
      else if (state === 'user') amplitude = readUserRef.current();

      smoothAmp = smoothAmp * 0.7 + amplitude * 0.3;

      // Lerp the accent toward the target for this state
      const target = ACCENTS[state];
      const targetIntensity = ACCENT_INTENSITY[state];
      for (let i = 0; i < 3; i++) accent[i] += (target[i] - accent[i]) * 0.08;
      accentIntensity += (targetIntensity - accentIntensity) * 0.08;

      // Amplitude-reactive center glow in the accent color
      const glowRadius = 120 + smoothAmp * 90;
      const glowAlpha = (0.12 + smoothAmp * 0.28) * accentIntensity;
      const [r, g, b] = accent;
      const gradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, glowRadius);
      gradient.addColorStop(0, `rgba(${r | 0}, ${g | 0}, ${b | 0}, ${glowAlpha})`);
      gradient.addColorStop(1, `rgba(${r | 0}, ${g | 0}, ${b | 0}, 0)`);
      ctx.fillStyle = gradient;
      ctx.globalAlpha = 1;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      particles.forEach((p) => {
        p.update(state, smoothAmp, accent, accentIntensity);
        p.draw(ctx);
      });

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', resizeCanvas);
      particles = [];
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="relative w-full max-w-4xl h-[50vh] flex items-center justify-center"
    >
      <canvas
        ref={canvasRef}
        className="w-full h-full object-contain"
        style={{ filter: 'contrast(120%)' }}
      />
    </div>
  );
}

// ─── Transcript ──────────────────────────────────────────────────────

function TranscriptDisplay() {
  const transcriptions = useTranscriptions();
  const scrollRef = useRef<HTMLDivElement>(null);

  // STT streams arrive as many small segments. Rendering each as its own
  // line reads like choppy bullets — instead, coalesce consecutive segments
  // from the same speaker into one flowing utterance. A new visual line
  // starts only when the speaker changes (i.e. turn-taking), so chunk
  // boundaries are invisible to the reader.
  const turns: { isUser: boolean; text: string; key: string }[] = [];
  for (const item of transcriptions) {
    const text = item.text.trim();
    if (!text) continue;
    const isUser = item.participantInfo.identity.startsWith('visitor-');
    const last = turns[turns.length - 1];
    if (last && last.isUser === isUser) {
      last.text += (last.text.endsWith(' ') ? '' : ' ') + text;
    } else {
      turns.push({ isUser, text, key: item.streamInfo?.id ?? String(turns.length) });
    }
  }

  const totalChars = turns.reduce((n, t) => n + t.text.length, 0);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
    // Track content growth (interim segments update text without changing count)
  }, [totalChars]);

  return (
    <div
      ref={scrollRef}
      className="mt-8 w-full max-w-2xl px-6 space-y-3 text-center z-10 max-h-[26vh] overflow-y-auto scrollbar-hide"
    >
      {turns.map((turn) =>
        turn.isUser ? (
          <div key={turn.key} className="text-[#555555] text-sm md:text-base opacity-80">
            ~ {turn.text}
          </div>
        ) : (
          <div
            key={turn.key}
            className="text-white text-base md:text-lg font-medium leading-relaxed flex items-start justify-center gap-3"
          >
            <span className="text-brand-red mt-0.5">&gt;</span>
            <span>{turn.text}</span>
          </div>
        )
      )}
    </div>
  );
}

// ─── Active session (inside LiveKitRoom context) ─────────────────────

function ActiveVoiceSession({
  onDisconnect,
  onAgentNoShow,
}: {
  onDisconnect: () => void;
  onAgentNoShow: () => void;
}) {
  const { state, audioTrack, agentAttributes } = useVoiceAssistant();
  const { microphoneTrack } = useLocalParticipant();

  const voiceState = mapAgentState(state);

  // Pick a fresh thinking verb each time the agent enters 'thinking' —
  // the memo re-evaluates exactly when isThinking flips. Randomness here is
  // deliberate (a different verb per episode), so the purity rule is waived.
  const isThinking = state === 'thinking';
  const thinkingWord = useMemo(
    () => THINKING_WORDS[Math.floor(Math.random() * THINKING_WORDS.length)],
    // eslint-disable-next-line react-hooks/exhaustive-deps -- isThinking keys the episode
    [isThinking]
  );

  // Degradation status published by the agent via participant attributes.
  // LLM fallback / TTS degraded: a tiny amber mark next to the listening
  // indicator (the full banner fired on the greeting-turn failover and read
  // as an error). TTS down still gets the banner — output is actually gone.
  const ttsStatus = agentAttributes?.['voice.tts'];
  const llmStatus = agentAttributes?.['voice.llm'];
  const ttsDown = ttsStatus === 'down';
  const showFallbackMark =
    llmStatus === 'fallback' || ttsStatus === 'degraded';
  const fallbackTitle =
    ttsStatus === 'degraded' ? 'fallback voice' : 'fallback model';
  const degradedMessage = ttsDown
    ? 'voice output unavailable — provider limits hit. try the chat tab'
    : null;

  const agentMediaTrack = (audioTrack as TrackReference | undefined)?.publication
    ?.track?.mediaStreamTrack;
  const userMediaTrack = (microphoneTrack as TrackPublication | undefined)?.track
    ?.mediaStreamTrack;

  const readAgentAmplitude = useTrackAmplitude(agentMediaTrack);
  const readUserAmplitude = useTrackAmplitude(userMediaTrack);

  const waitingForAgent =
    state === 'disconnected' || state === 'connecting' || state === undefined;

  useEffect(() => {
    if (!waitingForAgent) return;
    const timer = setTimeout(onAgentNoShow, AGENT_JOIN_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [waitingForAgent, onAgentNoShow]);

  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-black relative overflow-hidden font-mono">
      <ParticleField
        voiceState={voiceState}
        readAgentAmplitude={readAgentAmplitude}
        readUserAmplitude={readUserAmplitude}
      />

      {/* Session state indicator */}
      <div className="absolute top-6 left-6 flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${
            state === 'speaking'
              ? 'bg-green-500 animate-pulse'
              : state === 'listening'
                ? 'bg-brand-red animate-pulse'
                : state === 'thinking'
                  ? 'bg-amber-400 animate-pulse'
                  : 'bg-[#444444]'
          }`}
        />
        <span className="text-[#555555] text-[10px] tracking-[0.2em] uppercase">
          {waitingForAgent ? 'waiting for agent' : state}
        </span>
        {showFallbackMark && (
          <span
            className="inline-block h-1.5 w-1.5 bg-amber-400/70"
            title={fallbackTitle}
            aria-label={fallbackTitle}
          />
        )}
      </div>

      {/* TTS-down only — LLM fallback is the mark above, not a banner */}
      {degradedMessage && (
        <div className="absolute top-6 left-1/2 -translate-x-1/2 z-20 border border-amber-500/30 bg-amber-500/10 px-4 py-1.5">
          <span className="text-amber-400/90 text-[10px] tracking-[0.2em] uppercase">
            {degradedMessage}
          </span>
        </div>
      )}

      {waitingForAgent ? (
        <div className="mt-8 text-[#555555] text-xs tracking-[0.3em] uppercase animate-pulse z-10">
          Summoning the agent...
        </div>
      ) : (
        <>
          {state === 'thinking' && (
            <div className="mt-2 text-amber-400/70 text-xs tracking-[0.25em] uppercase animate-pulse z-10">
              {thinkingWord}…
            </div>
          )}
          <TranscriptDisplay />
        </>
      )}

      <footer className="absolute bottom-8 w-full flex justify-center">
        <button
          onClick={onDisconnect}
          className="text-[#555555] text-[10px] tracking-[0.2em] uppercase hover:text-brand-red/70 transition-colors cursor-pointer"
        >
          [ ESC TO DISCONNECT ]
        </button>
      </footer>
    </div>
  );
}

// ─── Pre-connection views ────────────────────────────────────────────

// Idle amplitude readers are inert — the 'idle' particle state drifts and never
// samples amplitude, so these constants keep ParticleField's contract satisfied
// without wiring up any audio analyser before a connection exists.
const IDLE_AMPLITUDE = () => 0;

function IdleView({ onStart }: { onStart: () => void }) {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-black relative overflow-hidden font-mono">
      {/* Quiet particle field at rest behind the button (design brief: "still
          surface just before something breaks through it"). Pointer-events off
          so it never intercepts the button. */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-70">
        <ParticleField
          voiceState="idle"
          readAgentAmplitude={IDLE_AMPLITUDE}
          readUserAmplitude={IDLE_AMPLITUDE}
        />
        {/* Single pulsing red heartbeat at the field's core (design brief) */}
        <span className="absolute w-1.5 h-1.5 rounded-full bg-brand-red animate-pulse" />
      </div>
      <div className="text-center z-10">
        <div className="w-20 h-20 mx-auto mb-8 rounded-full border border-brand-red/20 flex items-center justify-center">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" className="text-brand-red/60">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3Z" fill="currentColor" />
            <path
              d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        </div>
        <button
          onClick={onStart}
          className="group relative overflow-hidden border border-[#1F1F1F] px-8 py-4 font-mono text-sm uppercase tracking-widest transition-colors duration-300 hover:border-brand-red/50 text-white cursor-pointer"
        >
          <div className="absolute inset-0 translate-y-full bg-brand-red/10 transition-transform duration-300 ease-out group-hover:translate-y-0" />
          <span className="relative z-10 flex items-center gap-3">
            <span className="text-brand-red">&gt;</span>
            Start Voice
          </span>
        </button>
        <p className="mt-6 text-[#555555] text-[10px] tracking-[0.2em] uppercase">
          Talk to an AI version of Paymanshu
        </p>
      </div>
    </div>
  );
}

function MicPermissionModal({
  onGranted,
  onCancel,
}: {
  onGranted: () => void;
  onCancel: () => void;
}) {
  const [requesting, setRequesting] = useState(false);
  const [denied, setDenied] = useState(false);

  const handleAllow = async () => {
    setRequesting(true);
    setDenied(false);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Release immediately — LiveKit publishes its own track on connect
      stream.getTracks().forEach((t) => t.stop());
      // Remember the grant so the modal is a one-time experience
      try {
        localStorage.setItem(MIC_GRANTED_KEY, '1');
      } catch {
        /* storage unavailable (private mode) — modal will show again */
      }
      onGranted();
    } catch {
      setDenied(true);
      setRequesting(false);
    }
  };

  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;

  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-black relative font-mono">
      {/* Points at where the browser shows its native permission prompt */}
      <div
        className={`absolute top-4 ${isMobile ? 'left-1/2 -translate-x-1/2' : 'left-8'} animate-bounce`}
      >
        <svg
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          className="text-brand-red"
          style={{ transform: isMobile ? 'rotate(0deg)' : 'rotate(-45deg)' }}
        >
          <path
            d="M12 4L12 20M12 4L6 10M12 4L18 10"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span className="text-brand-red/70 text-[10px] tracking-widest uppercase mt-1 block text-center">
          Allow here
        </span>
      </div>

      <div className="max-w-md mx-auto px-8 py-10 border border-[#1F1F1F] bg-[#111111]/40 backdrop-blur-sm text-center">
        <div className="w-16 h-16 mx-auto mb-6 rounded-full border border-brand-red/30 flex items-center justify-center">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="text-brand-red">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3Z" fill="currentColor" />
            <path
              d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        </div>

        <h3 className="text-white text-lg font-light mb-3">Microphone Access</h3>
        <p className="text-[#888888] text-sm leading-relaxed mb-6">
          This voice chat lets you talk with an AI version of me. Your audio is
          processed in real-time and <span className="text-white">never stored</span>.
        </p>

        {denied && (
          <p className="text-brand-red/80 text-xs mb-4">
            Microphone access denied — check your browser permissions and retry.
          </p>
        )}

        <div className="flex flex-col gap-3">
          <button
            onClick={handleAllow}
            disabled={requesting}
            className="w-full px-6 py-3 bg-brand-red/10 border border-brand-red/30 text-brand-red text-xs uppercase tracking-widest font-mono hover:bg-brand-red/20 hover:border-brand-red/50 transition-all duration-300 disabled:opacity-50 disabled:cursor-wait cursor-pointer"
          >
            {requesting ? 'Requesting Access...' : 'Enable Microphone'}
          </button>
          <button
            onClick={onCancel}
            className="w-full px-6 py-3 text-[#888888] text-xs uppercase tracking-widest font-mono hover:text-white transition-colors duration-300 cursor-pointer"
          >
            Cancel
          </button>
        </div>
      </div>

      <p className="absolute bottom-8 text-[#555555] text-[10px] tracking-[0.2em] uppercase">
        Voice powered by LiveKit WebRTC
      </p>
    </div>
  );
}

function ConnectingView() {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-black font-mono">
      <div className="text-brand-red text-xs tracking-[0.3em] uppercase animate-pulse">
        Establishing Connection...
      </div>
    </div>
  );
}

/**
 * Shown when the voice agent is not available — either no backend is
 * configured for this build, or it is configured but unreachable.
 *
 * This is a first-class state, not an error. The tab stays visible and the
 * particle field keeps running (slower, cold-accented) so the interface still
 * reads as designed rather than broken. No retry button when there is nothing
 * to retry against; no mention of the backend or its URL.
 */
function RestingView({ onRetry }: { onRetry?: () => void }) {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-black relative overflow-hidden font-mono">
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-50">
        <ParticleField
          voiceState="resting"
          readAgentAmplitude={IDLE_AMPLITUDE}
          readUserAmplitude={IDLE_AMPLITUDE}
        />
      </div>

      <div className="text-center z-10 px-6">
        {/* Same mic silhouette as idle, muted and struck through — the
            affordance is recognisably the same object, just off duty. */}
        <div className="w-20 h-20 mx-auto mb-8 rounded-full border border-[#3A4A5C]/40 flex items-center justify-center">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" className="text-[#607A94]/70">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3Z" fill="currentColor" />
            <path
              d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
            <path d="M3 3l18 18" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </div>

        <p className="text-[#8FA8C0] text-sm tracking-[0.2em] uppercase mb-3">
          Agent Resting
        </p>
        <p className="text-[#555555] text-xs max-w-xs mx-auto leading-relaxed">
          The live voice agent is off duty right now — come back later!
        </p>
        <p className="mt-6 text-[#444444] text-[10px] tracking-[0.2em] uppercase">
          Try the chat or PDF tab meanwhile
        </p>

        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-8 border border-[#1F1F1F] px-6 py-2 text-xs uppercase tracking-widest text-[#666666] hover:text-[#8FA8C0] hover:border-[#3A4A5C]/50 transition-colors cursor-pointer"
          >
            Check Again
          </button>
        )}
      </div>
    </div>
  );
}

function formatBackAt(reason: VoiceUnavailableReason, backAt?: string): string | null {
  if (!backAt) return null;
  const when = new Date(backAt);
  if (Number.isNaN(when.getTime())) return null;
  return reason === 'daily_limit'
    ? when.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
    : when.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

function unavailableCopy(
  reason: VoiceUnavailableReason,
  backAt?: string
): { title: string; body: string; canRetry: boolean } {
  const back = formatBackAt(reason, backAt);
  switch (reason) {
    case 'busy':
      return {
        title: 'Line is busy',
        body:
          'Too many people are talking to me right now (somehow). Give it a few minutes, or ask the terminal. Same brain, more typing.',
        canRetry: true,
      };
    case 'monthly_limit':
      return {
        title: 'Out of minutes',
        body: `I've blown through my voice limits for the month (also likely). AI me is back${
          back ? ` around ${back}` : ' next month'
        }. The terminal still works.`,
        canRetry: false,
      };
    case 'daily_limit':
      return {
        title: 'Done talking for today',
        body: `Voice hit its daily cap. Back${back ? ` at ${back}` : ' tomorrow'}. The terminal is still up.`,
        canRetry: false,
      };
    case 'disabled':
      return {
        title: 'Voice is off',
        body: "I've switched voice off for now. The terminal is still up.",
        canRetry: false,
      };
    case 'no_show':
      return {
        title: "AI me didn't show up",
        body:
          'Either every line just filled up or something broke on my end. Try again in a minute, or use the terminal.',
        canRetry: true,
      };
  }
}

function WaitlistForm({ reason }: { reason: VoiceUnavailableReason }) {
  const [email, setEmail] = useState('');
  const [phase, setPhase] = useState<'idle' | 'sending' | 'done' | 'invalid' | 'error'>('idle');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (phase === 'sending' || phase === 'done') return;
    setPhase('sending');
    const result = await joinVoiceWaitlist(email.trim(), reason);
    setPhase(result === 'ok' ? 'done' : result);
    if (result === 'ok') trackEvent('voice_waitlist_join', { reason });
  };

  if (phase === 'done') {
    return (
      <p className="mt-6 text-[#8FA8C0] text-xs">
        Got it. I&apos;ll email you once when AI me is back.
      </p>
    );
  }

  return (
    <form onSubmit={submit} className="mt-6 flex flex-col items-center gap-2">
      <p className="text-[#555555] text-[10px] tracking-[0.2em] uppercase">
        Or get an email when I&apos;m back
      </p>
      <div className="flex w-full max-w-xs border border-[#1F1F1F] focus-within:border-[#3A4A5C]/60">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            if (phase === 'invalid' || phase === 'error') setPhase('idle');
          }}
          placeholder="you@somewhere.com"
          aria-label="Email address"
          className="min-w-0 flex-1 bg-transparent px-3 py-2 text-xs text-white placeholder:text-[#444444] outline-none"
        />
        <button
          type="submit"
          disabled={phase === 'sending'}
          className="px-4 text-[10px] uppercase tracking-widest text-[#8FA8C0] hover:text-white disabled:opacity-50 cursor-pointer"
        >
          {phase === 'sending' ? '...' : 'Notify me'}
        </button>
      </div>
      <p className="text-[#444444] text-[10px] max-w-xs leading-relaxed">
        {phase === 'invalid'
          ? "That doesn't look like an email."
          : phase === 'error'
            ? "Couldn't save that. Try the terminal instead?"
            : 'Used once to say it\'s back, maybe a hello later. No newsletter.'}
      </p>
    </form>
  );
}

/**
 * Voice is reachable but can't take a call: the 5-call cap, a daily or monthly
 * limit, the owner's kill switch, or an agent that never joined. Same cold
 * resting palette as RestingView, with the terminal as the first way out.
 */
function UnavailableView({
  reason,
  backAt,
  onUseTerminal,
  onRetry,
}: {
  reason: VoiceUnavailableReason;
  backAt?: string;
  onUseTerminal?: () => void;
  onRetry: () => void;
}) {
  const copy = unavailableCopy(reason, backAt);
  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-black relative overflow-hidden font-mono">
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-40">
        <ParticleField
          voiceState="resting"
          readAgentAmplitude={IDLE_AMPLITUDE}
          readUserAmplitude={IDLE_AMPLITUDE}
        />
      </div>

      <div className="text-center z-10 px-6 max-w-md">
        <p className="text-[#8FA8C0] text-sm tracking-[0.2em] uppercase mb-3">{copy.title}</p>
        <p className="text-[#777777] text-xs leading-relaxed">{copy.body}</p>

        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          {onUseTerminal && (
            <button
              onClick={onUseTerminal}
              className="group relative overflow-hidden border border-[#1F1F1F] px-6 py-2 text-xs uppercase tracking-widest text-white hover:border-brand-red/50 transition-colors cursor-pointer"
            >
              <span className="text-brand-red">&gt;</span> Open the terminal
            </button>
          )}
          {copy.canRetry && (
            <button
              onClick={onRetry}
              className="border border-[#1F1F1F] px-6 py-2 text-xs uppercase tracking-widest text-[#666666] hover:text-[#8FA8C0] hover:border-[#3A4A5C]/50 transition-colors cursor-pointer"
            >
              Try again
            </button>
          )}
        </div>

        <WaitlistForm reason={reason} />
      </div>
    </div>
  );
}

function ErrorView({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-black font-mono text-center px-6">
      <p className="text-brand-red text-sm mb-4">Connection Error</p>
      <p className="text-[#555555] text-xs mb-6 max-w-sm">{message}</p>
      <button
        onClick={onRetry}
        className="border border-[#1F1F1F] px-6 py-2 text-xs uppercase tracking-widest text-[#888888] hover:text-white hover:border-brand-red/30 transition-colors cursor-pointer"
      >
        Retry
      </button>
    </div>
  );
}

// ─── Top-level component ─────────────────────────────────────────────

type ConnectionState =
  | 'idle'
  | 'checking'
  | 'resting'
  | 'permission'
  | 'connecting'
  | 'connected'
  | 'unavailable'
  | 'error';

export default function VoiceResume({ onUseTerminal }: { onUseTerminal?: () => void } = {}) {
  const [connState, setConnState] = useState<ConnectionState>('idle');
  const [unavailable, setUnavailable] = useState<{
    reason: VoiceUnavailableReason;
    backAt?: string;
  }>({ reason: 'busy' });

  const showUnavailable = useCallback((reason: VoiceUnavailableReason, backAt?: string) => {
    setUnavailable({ reason, backAt });
    setConnState('unavailable');
    trackEvent('voice_unavailable', { reason });
  }, []);
  const [token, setToken] = useState('');
  const [wsUrl, setWsUrl] = useState('');
  const [error, setError] = useState('');
  const sessionStartedAt = useRef(0);

  const handlePermissionGranted = useCallback(async () => {
    setConnState('connecting');
    const endpoint = agentEndpoint('/api/token');
    if (!endpoint) {
      setConnState('resting');
      return;
    }

    try {
      const res = await fetch(endpoint, { method: 'POST' });
      if (res.status === 503) {
        const data = await res.json().catch(() => null);
        if (data?.reason && data.reason !== 'ok') {
          showUnavailable(data.reason, data.back_at);
          return;
        }
      }
      if (res.status === 429) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.error ?? 'Rate limited — try again in a minute.');
      }
      if (!res.ok) throw new Error(`Token server returned ${res.status}`);
      const data = await res.json();

      setToken(data.participantToken ?? data.token);
      setWsUrl(data.serverUrl ?? data.url);
      setConnState('connected');
      sessionStartedAt.current = Date.now();
      trackEvent('voice_session_start');
    } catch (err) {
      // A backend that is configured but unreachable is the resting state too,
      // not a red error screen — the visitor did nothing wrong and there is no
      // action for them to take. Genuine protocol errors (rate limits, bad
      // responses) still surface as errors with their message.
      const isUnreachable = err instanceof TypeError;
      if (isUnreachable) {
        setConnState('resting');
      } else {
        setError(
          err instanceof Error
            ? err.message
            : 'Could not reach the voice agent server.'
        );
        setConnState('error');
      }
      trackEvent('voice_error', { stage: 'token' });
    }
  }, [showUnavailable]);

  const handleDisconnect = useCallback(() => {
    if (sessionStartedAt.current) {
      trackEvent('voice_session_end', {
        duration_seconds: Math.round((Date.now() - sessionStartedAt.current) / 1000),
      });
      sessionStartedAt.current = 0;
    }
    setToken('');
    setWsUrl('');
    // Only a live session goes back to idle. LiveKitRoom also fires
    // onDisconnected while unmounting for the unavailable view, and that must
    // not overwrite it.
    setConnState((s) => (s === 'connected' ? 'idle' : s));
  }, []);

  const handleAgentNoShow = useCallback(() => {
    sessionStartedAt.current = 0;
    showUnavailable('no_show');
  }, [showUnavailable]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && connState === 'connected') {
        handleDisconnect();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [connState, handleDisconnect]);

  const handleStart = useCallback(async () => {
    // Availability is checked BEFORE anything touches the microphone. Asking
    // for mic access and only then discovering the agent is down is the worst
    // possible order: the visitor grants a sensitive permission and gets
    // nothing for it.
    if (!isAgentConfigured) {
      setConnState('resting');
      return;
    }

    setConnState('checking');
    const status = await fetchVoiceStatus();
    if (!status) {
      setConnState('resting');
      return;
    }
    if (!status.available && status.reason !== 'ok') {
      showUnavailable(status.reason, status.back_at);
      return;
    }

    // Skip the explainer modal entirely when mic access is already granted —
    // it should be a one-time experience per device.
    if (await isMicAlreadyGranted()) {
      void handlePermissionGranted();
    } else {
      setConnState('permission');
    }
  }, [handlePermissionGranted, showUnavailable]);

  switch (connState) {
    case 'idle':
      return <IdleView onStart={() => void handleStart()} />;
    case 'checking':
      return <ConnectingView />;
    case 'resting':
      return (
        <RestingView
          // Only offer a re-check when there is a backend to re-check against.
          onRetry={isAgentConfigured ? () => void handleStart() : undefined}
        />
      );
    case 'permission':
      return (
        <MicPermissionModal
          onGranted={handlePermissionGranted}
          onCancel={() => setConnState('idle')}
        />
      );
    case 'connecting':
      return <ConnectingView />;
    case 'unavailable':
      return (
        <UnavailableView
          reason={unavailable.reason}
          backAt={unavailable.backAt}
          onUseTerminal={onUseTerminal}
          onRetry={() => void handleStart()}
        />
      );
    case 'error':
      return <ErrorView message={error} onRetry={() => setConnState('idle')} />;
    case 'connected':
      return (
        <LiveKitRoom
          token={token}
          serverUrl={wsUrl}
          connect={true}
          audio={true}
          video={false}
          onDisconnected={handleDisconnect}
          onError={(e) => {
            setError(e.message);
            setConnState('error');
            trackEvent('voice_error', { stage: 'room' });
          }}
          className="w-full h-full"
        >
          <ActiveVoiceSession
            onDisconnect={handleDisconnect}
            onAgentNoShow={handleAgentNoShow}
          />
          <RoomAudioRenderer />
        </LiveKitRoom>
      );
  }
}
