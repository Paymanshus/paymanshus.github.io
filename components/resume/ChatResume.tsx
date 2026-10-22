'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { trackEvent } from '@/lib/analytics';
import { agentEndpoint, isAgentConfigured } from '@/lib/agent';
import { readChatStream } from '@/lib/chatStream';

const BOOT_SEQUENCE = [
  "INITIALIZING SYSTEM...",
  "LOADING KERNEL MODULES...",
  "MOUNTING VIRTUAL FILESYSTEM...",
  "ESTABLISHING SECURE CONNECTION...",
  "AUTHENTICATING USER...",
  "ACCESS GRANTED.",
  " ",
  "Welcome to PAYMANSHU_OS v2.6.0",
  "Type 'help' for commands, or just ask me anything about my experience.",
  " "
];

const RESPONSES: Record<string, string[]> = {
  help: [
    "AVAILABLE COMMANDS:",
    "  about      - Display personal information",
    "  skills     - List technical proficiencies",
    "  experience - Show work history",
    "  education  - Display academic background",
    "  clear      - Clear terminal output",
    "  contact    - Show contact information",
    " ",
    // Replaced at render time — see HELP_FREEFORM_LINE. Promising an LLM
    // answer when no backend is configured sets the visitor up to fail.
    "__FREEFORM__"
  ],
  about: [
    "NAME: Paymanshu Sharma",
    "ROLE: Machine Learning Engineer",
    "LOCATION: Bangalore, India",
    "STATUS: Building."
  ],
  skills: [
    "LANGUAGES: Python, TypeScript, SQL, C++",
    "ML / AI: LLM apps, agent workflows, NLP, multimodal systems",
    "APP STACK: React, Next.js, FastAPI, Tailwind CSS",
    "TOOLS: Git, Docker, AWS, LangGraph, Vercel"
  ],
  experience: [
    "[CURRENT] Machine Learning Engineer @ Maersk",
    "  - Building Shipment CoCaptain, an agentic AI shipment insights product",
    "  - Shipping full-stack work across React, LangGraph, and evaluation systems",
    " ",
    "[PREVIOUS] Hike, Mphasis NEXT Labs, research-driven AI roles",
    "  - Voice agents, document AI, mobile IDP, and multimodal ML systems",
    "  - See PDF mode for fuller resume detail"
  ],
  education: [
    "B.Tech. in Data Science",
    "MPSTME, NMIMS | Mumbai | 2018 - 2022",
    "Use the PDF tab for the complete formal resume."
  ],
  contact: [
    "EMAIL: paymanshus@gmail.com",
    "GITHUB: github.com/paymanshus",
    "LINKEDIN: linkedin.com/in/paymanshus"
  ]
};

// Keyword fallback for when the LLM backend is unreachable, rate-limited, or
// simply not configured for this build. Maps loose topic keywords onto the
// canned command outputs.
//
// Patterns deliberately avoid a trailing \b on stems that pluralise —
// /\bskill\b/ does NOT match "skills", which silently broke the single most
// likely question a visitor asks. Stems are left open-ended (\bskill) so
// "skill", "skills", "skillset" all land, while a leading \b still prevents
// matching inside unrelated words.
const KEYWORD_FALLBACKS: [RegExp, keyof typeof RESPONSES][] = [
  [
    /\b(maersk|hike|mphasis|current|job|jobs|work|worked|working|role|roles|intern|internship|compan|career|employ|experience|position|team)/i,
    'experience',
  ],
  [
    /\b(skill|stack|tech|language|python|typescript|javascript|sql|c\+\+|react|next\.?js|tool|framework|library|libraries|ml|ai|llm|agent|nlp|proficien|know|use)/i,
    'skills',
  ],
  [
    /\b(college|university|degree|degrees|study|studies|studied|education|educational|school|academic|btech|b\.tech|nmims|mpstme|graduat|major)/i,
    'education',
  ],
  [
    /\b(email|e-mail|contact|reach|linkedin|github|hire|hiring|connect|touch|message|phone|call)/i,
    'contact',
  ],
  [
    /\b(who|about|name|yourself|intro|introduce|bio|background|tell me|you do|based|location|live)/i,
    'about',
  ],
];

// What `help` promises about free-form questions, matched to what this build
// can actually deliver.
const HELP_FREEFORM_LINE = isAgentConfigured
  ? 'Or type a free-form question — an LLM with my resume loaded will answer.'
  : 'Or type a free-form question — answered from cached resume data.';

function resolveResponse(key: keyof typeof RESPONSES): string[] {
  return RESPONSES[key].map(line =>
    line === '__FREEFORM__' ? HELP_FREEFORM_LINE : line
  );
}

function keywordFallback(query: string): string[] {
  // Header wording depends on *why* we are offline. When no backend is
  // configured for this build there is nothing "unavailable" — saying so
  // reads like a fault. Never mention the backend URL either way.
  const header = isAgentConfigured
    ? '[OFFLINE MODE] LLM unavailable — closest match:'
    : '[LOCAL MODE] Answering from cached resume data — closest match:';

  for (const [pattern, key] of KEYWORD_FALLBACKS) {
    if (pattern.test(query)) {
      return [header, " ", ...resolveResponse(key)];
    }
  }

  return [
    isAgentConfigured
      ? "[OFFLINE MODE] LLM unavailable and no keyword match found."
      : "[LOCAL MODE] No cached answer matched that question.",
    "Try 'help' for structured commands, or the PDF tab for the full resume.",
  ];
}

type HistoryTurn = { role: 'user' | 'system'; text: string };

// History lines render via dangerouslySetInnerHTML (for the styled prompt
// prefix), so anything user- or LLM-authored must be escaped first.
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// Shown while a free-form query is in flight, rotated in a shuffled order so
// a visitor never sees the same line twice in a row.
const THINKING_MESSAGES = [
  "Triangulating",
  "Discombobulating",
  "Debating with self",
  "Zoning out (then back in)",
  "Thinking deep thoughts",
  "Strategizing",
  "Faking thinking really long",
  "Consulting the résumé oracle",
  "Overthinking it",
  "Rummaging through memories",
  "Connecting the dots",
  "Pretending to be busy",
  "Asking the rubber duck",
  "Counting backwards from infinity",
  "Untangling neurons",
  "Reticulating splines",
  "Reading the fine print",
];

const THINKING_ROTATE_MS = 1800;

function shuffled<T>(items: T[]): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function ThinkingLine() {
  const [order] = useState(() => shuffled(THINKING_MESSAGES));
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(
      () => setIndex(i => (i + 1) % order.length),
      THINKING_ROTATE_MS
    );
    return () => clearInterval(id);
  }, [order.length]);

  return (
    <div className="text-[#666666]" aria-live="polite">
      <span className="animate-pulse">{order[index]}...</span>
      <span className="terminal-cursor ml-1 align-[-0.15em]" />
    </div>
  );
}

export default function ChatResume() {
  const [history, setHistory] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [isBooting, setIsBooting] = useState(true);
  const [isThinking, setIsThinking] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const chatHistoryRef = useRef<HistoryTurn[]>([]);
  // Command history buffer — every submitted line, newest last. `cmdIndex` walks
  // it: null = live (editing `input`), otherwise an index into `cmdHistory`.
  const cmdHistoryRef = useRef<string[]>([]);
  const cmdIndexRef = useRef<number | null>(null);

  useEffect(() => {
    let currentLine = 0;
    const bootInterval = setInterval(() => {
      if (currentLine < BOOT_SEQUENCE.length) {
        // Capture before the async state updater runs — reading
        // BOOT_SEQUENCE[currentLine] inside setHistory skips lines
        const line = BOOT_SEQUENCE[currentLine];
        currentLine++;
        setHistory(prev => [...prev, line]);
      } else {
        clearInterval(bootInterval);
        setIsBooting(false);
      }
    }, 150);

    return () => clearInterval(bootInterval);
  }, []);

  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({
        top: scrollContainerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [history, isThinking]);

  const askLlm = useCallback(async (question: string) => {
    // No backend configured for this build (the usual case for the static
    // Pages deploy). Answer locally instead of firing a request that cannot
    // succeed — a failed fetch would surface the agent URL in the visitor's
    // console and network panel.
    const endpoint = agentEndpoint('/api/chat');
    if (!endpoint) {
      setHistory(prev => [...prev, ...keywordFallback(question), " "]);
      return;
    }
    const streamEndpoint = `${endpoint}/stream`;

    const body = JSON.stringify({
      message: question,
      history: chatHistoryRef.current.slice(-6),
    });
    const finish = (reply: string) => {
      chatHistoryRef.current.push({ role: 'user', text: question });
      chatHistoryRef.current.push({ role: 'system', text: reply });
      trackEvent('terminal_chat', { llm: true });
    };

    setIsThinking(true);
    // Streamed reply: text appears as the model writes it. `replyStart` is the
    // history index where this reply's lines begin, fixed on the first piece.
    let replyStart: number | null = null;
    let streamed = '';
    // The agent answered but no model could: retrying /api/chat would just
    // walk the same failing ladder again, so go straight to the local fallback.
    let llmUnavailable = false;
    const renderStreamed = () =>
      setHistory(prev => {
        if (replyStart === null) replyStart = prev.length;
        return [...prev.slice(0, replyStart), ...escapeHtml(streamed).split('\n')];
      });

    try {
      const res = await fetch(streamEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      });
      if (res.status === 429) {
        const data = await res.json().catch(() => ({ error: 'Rate limited.' }));
        setHistory(prev => [...prev, `[RATE LIMITED] ${data.error}`, " "]);
        return;
      }
      if (!res.ok) throw new Error(`stream ${res.status}`);

      await readChatStream(res, (ev) => {
        if ('delta' in ev) {
          setIsThinking(false);
          streamed += ev.delta;
          renderStreamed();
        } else if ('error' in ev) {
          llmUnavailable = true;
        }
      });
      if (!streamed.trim()) throw new Error('empty reply');
      setHistory(prev => [...prev, " "]);
      finish(streamed);
    } catch {
      if (streamed.trim()) {
        // Connection dropped mid-reply: keep what arrived.
        setHistory(prev => [...prev, " "]);
        finish(streamed);
      } else {
        // Stream unavailable (older agent, proxy trouble): one plain request,
        // then the offline keyword fallback.
        try {
          if (llmUnavailable) throw new Error('llm_unavailable');
          const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body,
          });
          if (!res.ok) throw new Error(`backend ${res.status}`);
          const data = await res.json();
          const reply: string = data.reply || '';
          if (!reply) throw new Error('empty reply');
          setHistory(prev => [...prev, ...escapeHtml(reply).split('\n'), " "]);
          finish(reply);
        } catch {
          setHistory(prev => [...prev, ...keywordFallback(question), " "]);
          // Offline keyword fallback — worth knowing how often the backend misses.
          trackEvent('terminal_chat', { llm: false });
        }
      }
    } finally {
      setIsThinking(false);
    }
  }, []);

  const handleCommand = (cmd: string) => {
    const trimmedCmd = cmd.trim().toLowerCase();
    if (!trimmedCmd || isThinking) return;

    setHistory(prev => [...prev, `<span class="text-brand-red glow-text">&gt;</span> ${escapeHtml(cmd)}`]);

    if (trimmedCmd === 'clear') {
      setHistory([]);
      trackEvent('terminal_command', { command: 'clear' });
      return;
    }

    const response = RESPONSES[trimmedCmd]
      ? resolveResponse(trimmedCmd as keyof typeof RESPONSES)
      : undefined;
    if (response) {
      setHistory(prev => [...prev, ...response, " "]);
      // Only built-in command names are sent — never free-text questions.
      trackEvent('terminal_command', { command: trimmedCmd });
    } else {
      // Free-form question → LLM backend with resume context
      void askLlm(cmd.trim());
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const submitted = input.trim();
      if (submitted) {
        const buf = cmdHistoryRef.current;
        // Skip storing an immediate duplicate of the last command.
        if (buf[buf.length - 1] !== submitted) buf.push(submitted);
      }
      cmdIndexRef.current = null;
      handleCommand(input);
      setInput('');
    } else if (e.key === 'ArrowUp') {
      const buf = cmdHistoryRef.current;
      if (buf.length === 0) return;
      e.preventDefault();
      const next = cmdIndexRef.current === null ? buf.length - 1 : Math.max(0, cmdIndexRef.current - 1);
      cmdIndexRef.current = next;
      setInput(buf[next]);
    } else if (e.key === 'ArrowDown') {
      const buf = cmdHistoryRef.current;
      if (cmdIndexRef.current === null) return;
      e.preventDefault();
      const next = cmdIndexRef.current + 1;
      if (next >= buf.length) {
        cmdIndexRef.current = null;
        setInput('');
      } else {
        cmdIndexRef.current = next;
        setInput(buf[next]);
      }
    }
  };

  return (
    <div
      className="flex h-full min-h-0 w-full flex-col bg-[#050505] font-mono text-sm text-[#a3a3a3]"
      onClick={() => inputRef.current?.focus()}
    >
      <div
        ref={scrollContainerRef}
        className="scrollbar-hide flex-1 overflow-y-auto px-6 py-6 md:px-8 md:py-8"
      >
        <div className="flex min-h-full w-full flex-col gap-1 leading-6">
          {history.map((line, i) => (
            <div
              key={i}
              className="max-w-full whitespace-pre-wrap break-words"
              dangerouslySetInnerHTML={{ __html: line }}
            />
          ))}

          {isThinking && (
            <ThinkingLine />
          )}

          {!isBooting && !isThinking && (
            <div className="mt-2 flex items-center gap-3 pr-2">
              <span className="text-brand-red glow-text shrink-0">&gt;</span>
              <div className="relative min-w-0 flex-1">
                <div
                  aria-hidden="true"
                  className="pointer-events-none min-h-6 whitespace-pre-wrap break-words text-[#f5f5f5]"
                >
                  {input}
                  <span className="terminal-cursor ml-1 align-[-0.15em]" />
                </div>
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className="absolute inset-0 min-w-0 w-full bg-transparent border-none outline-none text-transparent caret-transparent"
                  autoFocus
                  spellCheck={false}
                  autoComplete="off"
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
