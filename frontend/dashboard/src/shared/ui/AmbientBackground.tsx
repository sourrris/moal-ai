import { cn } from '../lib/cn';

type AmbientBackgroundProps = {
  variant?: 'hero' | 'app';
  className?: string;
};

export function AmbientBackground({ variant = 'app', className }: AmbientBackgroundProps) {
  const isHero = variant === 'hero';

  return (
    <div aria-hidden="true" className={cn('pointer-events-none absolute inset-0 overflow-hidden', className)}>
      <div
        className={cn(
          'absolute inset-0',
          isHero
            ? 'bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(245,245,245,0.92)_45%,rgba(245,242,239,0.96)_100%)]'
            : 'bg-[linear-gradient(180deg,rgba(255,255,255,0.92),rgba(245,245,245,0.9)_38%,rgba(245,242,239,0.94)_100%)]'
        )}
      />

      <div
        className={cn(
          'absolute -left-[8%] top-[-10%] h-[34rem] w-[34rem] rounded-full blur-3xl',
          isHero ? 'animate-ambient-float bg-[rgba(255,255,255,0.96)]' : 'animate-ambient-float bg-[rgba(255,255,255,0.84)]'
        )}
      />

      <div
        className={cn(
          'absolute right-[-12%] top-[8%] h-[28rem] w-[28rem] rounded-full blur-3xl',
          isHero
            ? 'animate-ambient-float-reverse bg-[rgba(245,242,239,0.92)]'
            : 'animate-ambient-float-reverse bg-[rgba(245,242,239,0.82)]'
        )}
      />

      <div
        className={cn(
          'absolute inset-x-0 top-0 h-[52%]',
          isHero
            ? 'bg-[radial-gradient(circle_at_24%_10%,rgba(255,255,255,0.96),transparent_48%),radial-gradient(circle_at_76%_18%,rgba(245,242,239,0.88),transparent_42%)]'
            : 'bg-[radial-gradient(circle_at_18%_6%,rgba(255,255,255,0.88),transparent_42%),radial-gradient(circle_at_82%_12%,rgba(245,242,239,0.72),transparent_38%)]'
        )}
      />

      <div className="absolute inset-0 opacity-[0.12] [background-image:linear-gradient(to_right,rgba(127,255,255,0.35)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,0,0,0.03)_1px,transparent_1px)] [background-size:72px_72px]" />

      <div
        className={cn(
          'absolute inset-x-[8%] top-[18%] h-px bg-[linear-gradient(90deg,transparent,rgba(119,113,105,0.24),transparent)]',
          isHero ? 'opacity-80' : 'opacity-60'
        )}
      />
    </div>
  );
}
