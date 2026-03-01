import { type CSSProperties, useEffect, useId, useRef } from 'react';

import { cn } from '../lib/cn';

type AmbientBackgroundProps = {
  variant?: 'hero' | 'app';
  className?: string;
};

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

export function AmbientBackground({ variant = 'app', className }: AmbientBackgroundProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const id = useId().replace(/:/g, '');
  const patternId = `ambient-dots-${id}`;
  const defaultY = variant === 'hero' ? 36 : 18;

  useEffect(() => {
    const root = rootRef.current;
    if (!root) {
      return;
    }

    const media = window.matchMedia('(prefers-reduced-motion: reduce)');

    let targetX = 50;
    let targetY = defaultY;
    let currentX = 50;
    let currentY = defaultY;
    let targetIntensity = variant === 'hero' ? 0.76 : 0.62;
    let currentIntensity = targetIntensity;
    let idleTimer: number | null = null;
    let raf = 0;

    const apply = () => {
      root.style.setProperty('--ambient-x', `${currentX.toFixed(2)}%`);
      root.style.setProperty('--ambient-y', `${currentY.toFixed(2)}%`);
      root.style.setProperty('--ambient-intensity', currentIntensity.toFixed(3));
    };

    const resetTarget = () => {
      targetX = 50;
      targetY = defaultY;
      targetIntensity = variant === 'hero' ? 0.66 : 0.52;
    };

    const setIdle = () => {
      if (idleTimer) {
        window.clearTimeout(idleTimer);
      }
      idleTimer = window.setTimeout(() => {
        targetIntensity = variant === 'hero' ? 0.68 : 0.54;
      }, 120);
    };

    const updateTarget = (clientX: number, clientY: number) => {
      const rect = root.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) {
        return;
      }
      targetX = clamp(((clientX - rect.left) / rect.width) * 100, 0, 100);
      targetY = clamp(((clientY - rect.top) / rect.height) * 100, 0, 100);
      targetIntensity = 1;
      setIdle();
    };

    const animate = () => {
      currentX += (targetX - currentX) * 0.1;
      currentY += (targetY - currentY) * 0.1;
      currentIntensity += (targetIntensity - currentIntensity) * 0.16;
      apply();
      raf = window.requestAnimationFrame(animate);
    };

    if (media.matches) {
      resetTarget();
      currentX = targetX;
      currentY = targetY;
      currentIntensity = variant === 'hero' ? 0.5 : 0.42;
      apply();
      return;
    }

    const handlePointerMove = (event: PointerEvent) => {
      if (event.pointerType === 'touch') {
        return;
      }
      updateTarget(event.clientX, event.clientY);
    };

    const handleTouchMove = (event: TouchEvent) => {
      const touch = event.touches[0];
      if (!touch) {
        return;
      }
      updateTarget(touch.clientX, touch.clientY);
    };

    const handleDocumentExit = (event: MouseEvent) => {
      if (!event.relatedTarget) {
        resetTarget();
      }
    };

    const handleVisibilityChange = () => {
      if (document.hidden) {
        resetTarget();
      }
    };

    apply();
    raf = window.requestAnimationFrame(animate);
    window.addEventListener('pointermove', handlePointerMove, { passive: true });
    window.addEventListener('touchmove', handleTouchMove, { passive: true });
    window.addEventListener('mouseout', handleDocumentExit, { passive: true });
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('touchmove', handleTouchMove);
      window.removeEventListener('mouseout', handleDocumentExit);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (idleTimer) {
        window.clearTimeout(idleTimer);
      }
    };
  }, [defaultY, variant]);

  const rootStyle = {
    '--ambient-x': '50%',
    '--ambient-y': `${defaultY}%`,
    '--ambient-intensity': variant === 'hero' ? '0.74' : '0.6'
  } as CSSProperties;

  return (
    <div
      ref={rootRef}
      aria-hidden="true"
      className={cn('pointer-events-none absolute inset-0 overflow-hidden', className)}
      style={rootStyle}
    >
      <div
        className={cn(
          'absolute inset-0',
          variant === 'hero'
            ? 'bg-[radial-gradient(circle_at_20%_15%,rgba(255,255,255,0.95),rgba(244,244,245,0.92)_42%,rgba(244,244,245,1)_72%)]'
            : 'bg-[radial-gradient(circle_at_10%_0%,rgba(255,255,255,0.96),rgba(244,244,245,0.94)_45%,rgba(244,244,245,1)_76%)]'
        )}
      />

      <div
        className={cn(
          'absolute inset-0 animate-ambient-drift bg-[radial-gradient(circle_at_70%_20%,rgba(161,161,170,0.12),transparent_38%),radial-gradient(circle_at_30%_80%,rgba(212,212,216,0.14),transparent_40%)]',
          variant === 'hero' ? 'opacity-80' : 'opacity-70'
        )}
      />

      <div
        className={cn(
          'absolute inset-0 motion-reduce:hidden bg-[radial-gradient(420px_circle_at_var(--ambient-x)_var(--ambient-y),rgba(24,24,27,0.11),transparent_62%),radial-gradient(300px_circle_at_var(--ambient-x)_var(--ambient-y),rgba(37,99,235,0.16),transparent_66%)] mix-blend-multiply transition-opacity duration-200',
          variant === 'hero' ? 'opacity-80' : 'opacity-70'
        )}
        style={{ opacity: 'calc(var(--ambient-intensity) * 0.9)' }}
      />

      <svg className="absolute inset-0 h-full w-full opacity-[0.16]" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id={patternId} width="26" height="26" patternUnits="userSpaceOnUse">
            <circle cx="2" cy="2" r="1" fill="#a1a1aa" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill={`url(#${patternId})`} />
      </svg>
    </div>
  );
}
