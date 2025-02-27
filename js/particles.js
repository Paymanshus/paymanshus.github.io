class Particle {
    constructor(canvas, options = {}) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');

        // Default options
        this.options = {
            count: options.count || 100,
            color: options.color || '#e74c3c',
            radius: options.radius || { min: 1, max: 3 },
            speed: options.speed || { min: 0.1, max: 0.5 },
            opacity: options.opacity || { min: 0.1, max: 0.5 },
            connectDistance: options.connectDistance || 120
        };

        this.particles = [];
        this.mouse = {
            x: null,
            y: null,
            radius: 150
        };

        this.init();
        this.animate();
        this.handleResize();
        this.handleMouseMove();
    }

    init() {
        // Set canvas size
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;

        // Create particles
        for (let i = 0; i < this.options.count; i++) {
            this.particles.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                radius: Math.random() * (this.options.radius.max - this.options.radius.min) + this.options.radius.min,
                speed: {
                    x: (Math.random() - 0.5) * (this.options.speed.max - this.options.speed.min) + this.options.speed.min,
                    y: (Math.random() - 0.5) * (this.options.speed.max - this.options.speed.min) + this.options.speed.min
                },
                opacity: Math.random() * (this.options.opacity.max - this.options.opacity.min) + this.options.opacity.min
            });
        }
    }

    animate() {
        requestAnimationFrame(this.animate.bind(this));
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        for (let i = 0; i < this.particles.length; i++) {
            const p = this.particles[i];

            // Update position
            p.x += p.speed.x;
            p.y += p.speed.y;

            // Boundary check
            if (p.x < 0 || p.x > this.canvas.width) p.speed.x *= -1;
            if (p.y < 0 || p.y > this.canvas.height) p.speed.y *= -1;

            // Mouse interaction
            if (this.mouse.x !== null && this.mouse.y !== null) {
                const dx = p.x - this.mouse.x;
                const dy = p.y - this.mouse.y;
                const distance = Math.sqrt(dx * dx + dy * dy);

                if (distance < this.mouse.radius) {
                    const angle = Math.atan2(dy, dx);
                    const force = (this.mouse.radius - distance) / this.mouse.radius;

                    p.x += Math.cos(angle) * force;
                    p.y += Math.sin(angle) * force;
                }
            }

            // Draw particle
            this.ctx.beginPath();
            this.ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
            this.ctx.fillStyle = `rgba(${this.hexToRgb(this.options.color)}, ${p.opacity})`;
            this.ctx.fill();

            // Connect particles
            for (let j = i + 1; j < this.particles.length; j++) {
                const p2 = this.particles[j];
                const dx = p.x - p2.x;
                const dy = p.y - p2.y;
                const distance = Math.sqrt(dx * dx + dy * dy);

                if (distance < this.options.connectDistance) {
                    this.ctx.beginPath();
                    this.ctx.strokeStyle = `rgba(${this.hexToRgb(this.options.color)}, ${(this.options.connectDistance - distance) / this.options.connectDistance * 0.2})`;
                    this.ctx.lineWidth = 0.5;
                    this.ctx.moveTo(p.x, p.y);
                    this.ctx.lineTo(p2.x, p2.y);
                    this.ctx.stroke();
                }
            }
        }
    }

    handleResize() {
        window.addEventListener('resize', () => {
            this.canvas.width = window.innerWidth;
            this.canvas.height = window.innerHeight;
            this.init();
        });
    }

    handleMouseMove() {
        window.addEventListener('mousemove', (e) => {
            this.mouse.x = e.x;
            this.mouse.y = e.y;
        });

        window.addEventListener('mouseout', () => {
            this.mouse.x = null;
            this.mouse.y = null;
        });
    }

    hexToRgb(hex) {
        // Remove # if present
        hex = hex.replace('#', '');

        // Convert 3-digit hex to 6-digit
        if (hex.length === 3) {
            hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
        }

        // Parse hex values
        const r = parseInt(hex.substring(0, 2), 16);
        const g = parseInt(hex.substring(2, 4), 16);
        const b = parseInt(hex.substring(4, 6), 16);

        return `${r}, ${g}, ${b}`;
    }
}

// Initialize particles when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('particles');
    if (canvas) {
        new Particle(canvas, {
            count: 80,
            color: '#e74c3c',
            radius: { min: 1, max: 3 },
            speed: { min: 0.1, max: 0.3 },
            opacity: { min: 0.1, max: 0.5 },
            connectDistance: 150
        });
    }
});