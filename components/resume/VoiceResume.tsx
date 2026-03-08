'use client';

import { useState, useEffect, useRef } from 'react';

type VoiceState = 'idle' | 'user' | 'system';

class Particle {
  x: number = 0;
  y: number = 0;
  size: number = 0;
  type: 'square' | 'cross' = 'square';
  color: string = '';
  opacity: number = 0;
  vx: number = 0;
  vy: number = 0;
  baseDist: number = 0;
  angle: number = 0;

  constructor(private canvas: HTMLCanvasElement) {
    this.reset();
  }

  reset() {
    const centerX = this.canvas.width / 2;
    const centerY = this.canvas.height / 2;
    
    this.angle = Math.random() * Math.PI * 2;
    // Power curve for density
    this.baseDist = Math.pow(Math.random(), 2.5) * Math.min(this.canvas.width, this.canvas.height) * 0.8; 
    
    this.x = centerX + Math.cos(this.angle) * this.baseDist;
    this.y = centerY + Math.sin(this.angle) * this.baseDist;
    
    this.size = Math.random() * 3 + 1;
    this.type = Math.random() > 0.8 ? 'cross' : 'square';
    
    this.updateColorAndOpacity(centerX, centerY);

    this.vx = (Math.random() - 0.5) * 0.2;
    this.vy = (Math.random() - 0.5) * 0.2;
  }

  updateColorAndOpacity(centerX: number, centerY: number) {
    const dist = Math.sqrt(Math.pow(this.x - centerX, 2) + Math.pow(this.y - centerY, 2));
    if (dist < 60) {
      this.color = '#ff2a2a'; // brand red
      this.opacity = 1;
    } else if (dist < 180) {
      this.color = '#ffffff';
      this.opacity = Math.max(0.1, 1 - (dist / 450));
    } else {
      this.color = '#e2e2e2';
      this.opacity = Math.max(0, 0.6 - (dist / 600));
    }
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
      ctx.moveTo(this.x - this.size/2, this.y);
      ctx.lineTo(this.x + this.size/2, this.y);
      ctx.moveTo(this.x, this.y - this.size/2);
      ctx.lineTo(this.x, this.y + this.size/2);
      ctx.stroke();
    }
  }

  update(state: VoiceState) {
    const centerX = this.canvas.width / 2;
    const centerY = this.canvas.height / 2;

    if (state === 'system') {
      // Expand slightly
      this.x += Math.cos(this.angle) * 1.5;
      this.y += Math.sin(this.angle) * 1.5;
    } else if (state === 'user') {
      // Contract slightly
      const dx = centerX - this.x;
      const dy = centerY - this.y;
      this.x += dx * 0.01;
      this.y += dy * 0.01;
    } else {
      // Idle drift
      this.x += this.vx;
      this.y += this.vy;
    }

    this.updateColorAndOpacity(centerX, centerY);
    
    if (Math.random() > 0.998) this.reset();
  }
}

export default function VoiceResume() {
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [transcript, setTranscript] = useState<{role: 'user' | 'system', text: string}[]>([]);
  const [typingText, setTypingText] = useState('');
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let particles: Particle[] = [];
    const particleCount = 2200;

    const resizeCanvas = () => {
      if (containerRef.current) {
        canvas.width = containerRef.current.clientWidth;
        canvas.height = containerRef.current.clientHeight;
      }
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    const init = () => {
      particles = [];
      for (let i = 0; i < particleCount; i++) {
        particles.push(new Particle(canvas));
      }
    };

    init();

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;

      // Draw subtle glow bloom
      const gradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, 120);
      gradient.addColorStop(0, 'rgba(255, 42, 42, 0.15)');
      gradient.addColorStop(1, 'rgba(255, 42, 42, 0)');
      ctx.fillStyle = gradient;
      ctx.globalAlpha = 1;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      particles.forEach(p => {
        p.update(voiceState);
        p.draw(ctx);
      });

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', resizeCanvas);
    };
  }, [voiceState]);

  // Mock interaction
  useEffect(() => {
    let isMounted = true;
    
    const typeText = async (text: string) => {
      setTypingText('');
      for (let i = 0; i <= text.length; i++) {
        if (!isMounted) return;
        setTypingText(text.slice(0, i));
        await new Promise(r => setTimeout(r, 30));
      }
      if (!isMounted) return;
      setTranscript(prev => [...prev, { role: 'system', text }]);
      setTypingText('');
    };

    const sequence = async () => {
      await new Promise(r => setTimeout(r, 1000));
      if (!isMounted) return;
      
      setVoiceState('system');
      await typeText("Initializing Neural Profile... SUCCESS");
      
      await new Promise(r => setTimeout(r, 1000));
      if (!isMounted) return;
      setVoiceState('idle');
      
      await new Promise(r => setTimeout(r, 1500));
      if (!isMounted) return;
      setVoiceState('user');
      setTranscript(prev => [...prev, { role: 'user', text: "what projects have you worked on in NLP?" }]);
      
      await new Promise(r => setTimeout(r, 1500));
      if (!isMounted) return;
      setVoiceState('system');
      await typeText("I've built several LLM-powered interfaces and real-time voice agents.");
      
      await new Promise(r => setTimeout(r, 2000));
      if (!isMounted) return;
      setVoiceState('idle');
    };
    
    sequence();
    
    return () => { isMounted = false; };
  }, []);

  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-[#000000] relative overflow-hidden font-mono">
      {/* Particle Field */}
      <div ref={containerRef} className="relative w-full max-w-4xl h-[50vh] flex items-center justify-center">
        <canvas 
          ref={canvasRef} 
          className="w-full h-full object-contain"
          style={{ filter: 'contrast(120%)' }}
        />
        {/* Center Glow Overlay */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-32 h-32 bg-brand-red/20 blur-[80px] rounded-full"></div>
        </div>
      </div>
      
      {/* Chat Transcript */}
      <section className="mt-8 w-full max-w-2xl px-6 space-y-4 text-center z-10">
        {transcript.map((msg, i) => (
          <div key={i}>
            {msg.role === 'user' ? (
              <div className="text-[#555555] text-sm md:text-base opacity-80">
                ~ {msg.text}
              </div>
            ) : (
              <div className="text-white text-base md:text-lg font-medium leading-relaxed flex items-start justify-center gap-3">
                <span className="text-brand-red mt-0.5">&gt;</span>
                <span className="text-white">{msg.text}</span>
              </div>
            )}
          </div>
        ))}
        
        {/* Typing indicator */}
        {typingText && (
          <div className="text-white text-base md:text-lg font-medium flex items-start justify-center gap-3">
            <span className="text-brand-red mt-0.5">&gt;</span>
            <span className="text-white">
              {typingText}
              <span className="inline-block w-2 h-5 bg-brand-red align-middle ml-1 terminal-cursor"></span>
            </span>
          </div>
        )}
      </section>
      
      {/* Footer */}
      <footer className="absolute bottom-8 w-full flex justify-center">
        <div className="text-[#555555] text-[10px] tracking-[0.2em] uppercase">
          [ ESC TO DISCONNECT ]
        </div>
      </footer>
      
      {/* Floating Decor */}
      <div className="absolute bottom-8 right-8 text-[#555555] opacity-30">
        <svg fill="currentColor" height="24" viewBox="0 0 24 24" width="24">
          <path d="M12 0L14.59 9.41L24 12L14.59 14.59L12 24L9.41 14.59L0 12L9.41 9.41L12 0Z"></path>
        </svg>
      </div>
    </div>
  );
}
