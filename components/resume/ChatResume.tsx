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
  "Welcome to PAYMANSHU_OS v2.0.4",
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
    "ROLE: Software Engineer & Designer",
    "LOCATION: Earth",
    "STATUS: Building austere, high-performance interfaces."
  ],
  skills: [
    "LANGUAGES: TypeScript, Python, Rust, Go",
    "FRONTEND: React, Next.js, Tailwind CSS, Framer Motion",
    "BACKEND: Node.js, Express, PostgreSQL, Redis",
    "TOOLS: Git, Docker, AWS, Vercel"
  ],
  experience: [
    "[2023 - PRESENT] Senior Frontend Engineer @ TechCorp",
    "  - Architected and rebuilt core web application",
    "  - Improved performance metrics by 40%",
    " ",
    "[2021 - 2023] Full Stack Developer @ StartupX",
    "  - Developed real-time collaboration features",
    "  - Managed CI/CD pipelines"
  ],
  education: [
    "B.S. Computer Science",
    "University of Technology, 2021"
  ],
  contact: [
    "EMAIL: paymanshus@gmail.com",
    "GITHUB: github.com/paymanshu",
    "LINKEDIN: linkedin.com/in/paymanshu"
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
