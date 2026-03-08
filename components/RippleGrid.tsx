'use client';

import { useEffect, useRef } from 'react';
import { Mesh, Program, Renderer, Triangle } from 'ogl';

type RippleGridProps = {
  enableRainbow?: boolean;
  gridColor?: string;
  rippleIntensity?: number;
  gridSize?: number;
  gridThickness?: number;
  fadeDistance?: number;
  vignetteStrength?: number;
  glowIntensity?: number;
  opacity?: number;
  gridRotation?: number;
  mouseInteraction?: boolean;
  mouseInteractionRadius?: number;
};

const DEFAULT_MOUSE = { x: 0.5, y: 0.5 };
const MOBILE_BREAKPOINT = 768;

type FloorPerspectiveMapping = {
  perspective: number;
  rotateX: number;
  scale: number;
};

function hexToRgb(hex: string): [number, number, number] {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);

  if (!result) {
    return [1, 1, 1];
  }

  return [
    parseInt(result[1], 16) / 255,
    parseInt(result[2], 16) / 255,
    parseInt(result[3], 16) / 255,
  ];
}

function getFloorPerspectiveMapping(): FloorPerspectiveMapping {
  if (typeof window !== 'undefined' && window.innerWidth <= MOBILE_BREAKPOINT) {
    return {
      perspective: 1050,
      rotateX: 70,
      scale: 1.55,
    };
  }

  return {
    perspective: 1500,
    rotateX: 68,
    scale: 1.28,
  };
}

function mapScreenYToPlaneY(screenY: number, planeHeight: number, mapping: FloorPerspectiveMapping) {
  const clampedScreenY = Math.max(0, screenY);
  const angle = (mapping.rotateX * Math.PI) / 180;
  const numerator = clampedScreenY * mapping.perspective;
  const denominator =
    mapping.scale *
    (Math.cos(angle) * mapping.perspective + clampedScreenY * Math.sin(angle));

  if (!planeHeight || denominator <= 0) {
    return 0;
  }

  return numerator / denominator / planeHeight;
}

export default function RippleGrid({
  enableRainbow = false,
  gridColor = '#ffffff',
  rippleIntensity = 0.05,
  gridSize = 10,
  gridThickness = 15,
  fadeDistance = 1.5,
  vignetteStrength = 2,
  glowIntensity = 0.1,
  opacity = 1,
  gridRotation = 0,
  mouseInteraction = true,
  mouseInteractionRadius = 1,
}: RippleGridProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const uniformsRef = useRef<Record<string, { value: unknown }> | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const mousePositionRef = useRef(DEFAULT_MOUSE);
  const targetMouseRef = useRef(DEFAULT_MOUSE);
  const mouseInfluenceRef = useRef(0);

  useEffect(() => {
    const container = containerRef.current;

    if (!container) {
      return;
    }

    const renderer = new Renderer({
      alpha: true,
      dpr: Math.min(window.devicePixelRatio, 2),
    });

    const gl = renderer.gl;
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.canvas.style.width = '100%';
    gl.canvas.style.height = '100%';
    gl.canvas.style.pointerEvents = 'none';
    container.appendChild(gl.canvas);

    const vertex = `
attribute vec2 position;
varying vec2 vUv;

void main() {
  vUv = position * 0.5 + 0.5;
  gl_Position = vec4(position, 0.0, 1.0);
}`;

    const fragment = `precision highp float;
uniform float iTime;
uniform vec2 iResolution;
uniform bool enableRainbow;
uniform vec3 gridColor;
uniform float rippleIntensity;
uniform float gridSize;
uniform float gridThickness;
uniform float fadeDistance;
uniform float vignetteStrength;
uniform float glowIntensity;
uniform float opacity;
uniform float gridRotation;
uniform bool mouseInteraction;
uniform vec2 mousePosition;
uniform float mouseInfluence;
uniform float mouseInteractionRadius;
varying vec2 vUv;

float pi = 3.141592;

mat2 rotate(float angle) {
  float s = sin(angle);
  float c = cos(angle);
  return mat2(c, -s, s, c);
}

void main() {
  vec2 uv = vUv * 2.0 - 1.0;
  uv.x *= iResolution.x / iResolution.y;

  if (gridRotation != 0.0) {
    uv = rotate(gridRotation * pi / 180.0) * uv;
  }

  float dist = length(uv);
  float wave = sin(pi * (iTime - dist));
  vec2 rippleUv = uv + uv * wave * rippleIntensity;

  if (mouseInteraction && mouseInfluence > 0.0) {
    vec2 mouseUv = mousePosition * 2.0 - 1.0;
    mouseUv.x *= iResolution.x / iResolution.y;
    float mouseDist = length(uv - mouseUv);

    float influence = mouseInfluence * exp(-mouseDist * mouseDist / (mouseInteractionRadius * mouseInteractionRadius));
    float mouseWave = sin(pi * (iTime * 2.0 - mouseDist * 3.0)) * influence;
    rippleUv += normalize(uv - mouseUv) * mouseWave * rippleIntensity * 0.3;
  }

  vec2 waveGrid = sin(gridSize * 0.5 * pi * rippleUv - pi / 2.0);
  vec2 distanceToGrid = abs(waveGrid);

  float aaWidth = 0.5;
  vec2 smoothGrid = vec2(
    smoothstep(0.0, aaWidth, distanceToGrid.x),
    smoothstep(0.0, aaWidth, distanceToGrid.y)
  );

  vec3 color = vec3(0.0);
  color += exp(-gridThickness * smoothGrid.x * (0.8 + 0.5 * sin(pi * iTime)));
  color += exp(-gridThickness * smoothGrid.y);
  color += 0.5 * exp(-(gridThickness / 4.0) * sin(smoothGrid.x));
  color += 0.5 * exp(-(gridThickness / 3.0) * smoothGrid.y);

  if (glowIntensity > 0.0) {
    color += glowIntensity * exp(-gridThickness * 0.5 * smoothGrid.x);
    color += glowIntensity * exp(-gridThickness * 0.5 * smoothGrid.y);
  }

  float fade = exp(-2.0 * clamp(pow(dist, fadeDistance), 0.0, 1.0));

  vec2 vignetteCoords = vUv - 0.5;
  float vignetteDistance = length(vignetteCoords);
  float vignette = 1.0 - pow(vignetteDistance * 2.0, vignetteStrength);
  vignette = clamp(vignette, 0.0, 1.0);

  vec3 tint;
  if (enableRainbow) {
    tint = vec3(
      uv.x * 0.5 + 0.5 * sin(iTime),
      uv.y * 0.5 + 0.5 * cos(iTime),
      pow(cos(iTime), 4.0)
    ) + 0.5;
  } else {
    tint = gridColor;
  }

  float finalFade = fade * vignette;
  float alpha = length(color) * finalFade * opacity;
  gl_FragColor = vec4(color * tint * finalFade * opacity, alpha);
}`;

    const uniforms = {
      iTime: { value: 0 },
      iResolution: { value: [1, 1] },
      enableRainbow: { value: enableRainbow },
      gridColor: { value: hexToRgb(gridColor) },
      rippleIntensity: { value: rippleIntensity },
      gridSize: { value: gridSize },
      gridThickness: { value: gridThickness },
      fadeDistance: { value: fadeDistance },
      vignetteStrength: { value: vignetteStrength },
      glowIntensity: { value: glowIntensity },
      opacity: { value: opacity },
      gridRotation: { value: gridRotation },
      mouseInteraction: { value: mouseInteraction },
      mousePosition: { value: [DEFAULT_MOUSE.x, DEFAULT_MOUSE.y] },
      mouseInfluence: { value: 0 },
      mouseInteractionRadius: { value: mouseInteractionRadius },
    };

    uniformsRef.current = uniforms;

    const geometry = new Triangle(gl);
    const program = new Program(gl, {
      fragment,
      uniforms,
      vertex,
    });
    const mesh = new Mesh(gl, { geometry, program });

    const resize = () => {
      const { clientHeight, clientWidth } = container;
      renderer.setSize(clientWidth, clientHeight);
      uniforms.iResolution.value = [clientWidth, clientHeight];
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (!mouseInteraction) {
        return;
      }

      const rect = container.getBoundingClientRect();

      if (!rect.width || !rect.height) {
        return;
      }

      const nextX = (event.clientX - rect.left) / rect.width;
      const screenY = event.clientY - rect.top;
      const isInside = nextX >= 0 && nextX <= 1 && screenY >= 0 && screenY <= rect.height;

      if (!isInside) {
        mouseInfluenceRef.current = 0;
        return;
      }

      const planeHeight = container.clientHeight || rect.height;
      const mappedPlaneY = mapScreenYToPlaneY(
        screenY,
        planeHeight,
        getFloorPerspectiveMapping(),
      );
      const nextY = 1 - mappedPlaneY;

      targetMouseRef.current = {
        x: Math.max(0, Math.min(1, nextX)),
        y: Math.max(0, Math.min(1, nextY)),
      };
      mouseInfluenceRef.current = 1;
    };

    const handlePointerLeave = () => {
      mouseInfluenceRef.current = 0;
    };

    window.addEventListener('resize', resize);
    if (mouseInteraction) {
      window.addEventListener('pointermove', handlePointerMove);
      window.addEventListener('pointerleave', handlePointerLeave);
    }
    resize();

    const render = (time: number) => {
      uniforms.iTime.value = time * 0.001;

      mousePositionRef.current = {
        x: mousePositionRef.current.x + (targetMouseRef.current.x - mousePositionRef.current.x) * 0.1,
        y: mousePositionRef.current.y + (targetMouseRef.current.y - mousePositionRef.current.y) * 0.1,
      };

      uniforms.mouseInfluence.value += (mouseInfluenceRef.current - (uniforms.mouseInfluence.value as number)) * 0.05;
      uniforms.mousePosition.value = [mousePositionRef.current.x, mousePositionRef.current.y];

      renderer.render({ scene: mesh });
      animationFrameRef.current = window.requestAnimationFrame(render);
    };

    animationFrameRef.current = window.requestAnimationFrame(render);

    return () => {
      window.removeEventListener('resize', resize);
      if (mouseInteraction) {
        window.removeEventListener('pointermove', handlePointerMove);
        window.removeEventListener('pointerleave', handlePointerLeave);
      }

      if (animationFrameRef.current !== null) {
        window.cancelAnimationFrame(animationFrameRef.current);
      }

      renderer.gl.getExtension('WEBGL_lose_context')?.loseContext();

      if (container.contains(gl.canvas)) {
        container.removeChild(gl.canvas);
      }
    };
  }, [
    enableRainbow,
    fadeDistance,
    glowIntensity,
    gridColor,
    gridRotation,
    gridSize,
    gridThickness,
    mouseInteraction,
    mouseInteractionRadius,
    opacity,
    rippleIntensity,
    vignetteStrength,
  ]);

  useEffect(() => {
    if (!uniformsRef.current) {
      return;
    }

    uniformsRef.current.enableRainbow.value = enableRainbow;
    uniformsRef.current.gridColor.value = hexToRgb(gridColor);
    uniformsRef.current.rippleIntensity.value = rippleIntensity;
    uniformsRef.current.gridSize.value = gridSize;
    uniformsRef.current.gridThickness.value = gridThickness;
    uniformsRef.current.fadeDistance.value = fadeDistance;
    uniformsRef.current.vignetteStrength.value = vignetteStrength;
    uniformsRef.current.glowIntensity.value = glowIntensity;
    uniformsRef.current.opacity.value = opacity;
    uniformsRef.current.gridRotation.value = gridRotation;
    uniformsRef.current.mouseInteraction.value = mouseInteraction;
    uniformsRef.current.mouseInteractionRadius.value = mouseInteractionRadius;
  }, [
    enableRainbow,
    fadeDistance,
    glowIntensity,
    gridColor,
    gridRotation,
    gridSize,
    gridThickness,
    mouseInteraction,
    mouseInteractionRadius,
    opacity,
    rippleIntensity,
    vignetteStrength,
  ]);

  return <div ref={containerRef} className="relative h-full w-full overflow-hidden [&_canvas]:block" />;
}
