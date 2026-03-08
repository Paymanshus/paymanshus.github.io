'use client';

import { useState, useEffect, useRef } from 'react';

const BOOT_SEQUENCE = [
  "INITIALIZING SYSTEM...",
  "LOADING KERNEL MODULES...",
  "MOUNTING VIRTUAL FILESYSTEM...",
  "ESTABLISHING SECURE CONNECTION...",
  "AUTHENTICATING USER...",
  "ACCESS GRANTED.",
  " ",
  "Welcome to PAYMANSHU_OS v2.6.0",
  "Type 'help' to see available commands.",
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
    "  contact    - Show contact information"
  ],
  about: [
    "NAME: Paymanshu Sharma",
    "ROLE: Machine Learning Engineer",
    "LOCATION: Bangalore, India",
    "STATUS: Building." // AI-native products across LLM systems, voice agents, and full-stack interfaces
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

export default function ChatResume() {
  const [history, setHistory] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [isBooting, setIsBooting] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let currentLine = 0;
    const bootInterval = setInterval(() => {
      if (currentLine < BOOT_SEQUENCE.length) {
        setHistory(prev => [...prev, BOOT_SEQUENCE[currentLine]]);
        currentLine++;
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
  }, [history]);

  const handleCommand = (cmd: string) => {
    const trimmedCmd = cmd.trim().toLowerCase();
    if (!trimmedCmd) return;

    setHistory(prev => [...prev, `<span class="text-brand-red glow-text">&gt;</span> ${cmd}`]);

    if (trimmedCmd === 'clear') {
      setHistory([]);
      return;
    }

    const response = RESPONSES[trimmedCmd];
    if (response) {
      setHistory(prev => [...prev, ...response, " "]);
    } else {
      setHistory(prev => [...prev, `Command not found: ${trimmedCmd}`, "Type 'help' for available commands.", " "]);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleCommand(input);
      setInput('');
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

          {!isBooting && (
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
