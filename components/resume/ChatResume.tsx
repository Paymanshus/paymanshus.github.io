'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

const AGENT_SERVER_URL =
  process.env.NEXT_PUBLIC_AGENT_URL || 'http://localhost:8080';

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
    "Or type a free-form question — an LLM with my resume loaded will answer."
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

// Keyword fallback when the LLM backend is unreachable or rate-limited.
// Maps loose topic keywords onto the canned command outputs.
const KEYWORD_FALLBACKS: [RegExp, keyof typeof RESPONSES][] = [
  [/\b(maersk|current|job|work|role|hike|intern|company|companies|career)\b/i, 'experience'],
  [/\b(skill|stack|language|python|typescript|react|tool|framework|ml|ai|llm)\b/i, 'skills'],
  [/\b(college|university|degree|study|studied|education|school|btech|b\.tech)\b/i, 'education'],
  [/\b(email|contact|reach|linkedin|github|hire)\b/i, 'contact'],
  [/\b(who|about|name|yourself|intro)\b/i, 'about'],
];

function keywordFallback(query: string): string[] {
  for (const [pattern, key] of KEYWORD_FALLBACKS) {
    if (pattern.test(query)) {
      return [
        "[OFFLINE MODE] LLM unavailable — closest match:",
        " ",
        ...RESPONSES[key],
      ];
    }
  }
  return [
    "[OFFLINE MODE] LLM unavailable and no keyword match found.",
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
    setIsThinking(true);
    try {
      const res = await fetch(`${AGENT_SERVER_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: question,
          history: chatHistoryRef.current.slice(-6),
        }),
      });

      if (res.status === 429) {
        const data = await res.json().catch(() => ({ error: 'Rate limited.' }));
        setHistory(prev => [...prev, `[RATE LIMITED] ${data.error}`, " "]);
        return;
      }
      if (!res.ok) throw new Error(`backend ${res.status}`);

      const data = await res.json();
      const reply: string = data.reply || '';
      if (!reply) throw new Error('empty reply');

      chatHistoryRef.current.push({ role: 'user', text: question });
      chatHistoryRef.current.push({ role: 'system', text: reply });
      setHistory(prev => [...prev, ...escapeHtml(reply).split('\n'), " "]);
    } catch {
      setHistory(prev => [...prev, ...keywordFallback(question), " "]);
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
      return;
    }

    const response = RESPONSES[trimmedCmd];
    if (response) {
      setHistory(prev => [...prev, ...response, " "]);
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
            <div className="text-[#666666] animate-pulse">
              PROCESSING QUERY<span className="terminal-cursor ml-1 align-[-0.15em]" />
            </div>
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
                  style={{ caretColor: '#ff2a2a' }}
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
