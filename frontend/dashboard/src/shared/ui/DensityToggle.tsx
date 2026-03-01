import { useUI } from '../../app/state/ui-context';
import { cn } from '../lib/cn';

type DensityOption = 'compact' | 'comfortable';

const OPTIONS: Array<{ value: DensityOption; label: string }> = [
  { value: 'compact', label: 'Dense' },
  { value: 'comfortable', label: 'Comfort' }
];

export function DensityToggle({ className }: { className?: string }) {
  const { density, setDensity } = useUI();

  return (
    <div className={cn('density-toggle', className)} role="group" aria-label="Density mode">
      {OPTIONS.map((item) => (
        <button
          key={item.value}
          type="button"
          className={cn('density-toggle-btn', density === item.value && 'density-toggle-btn--active')}
          onClick={() => setDensity(item.value)}
          aria-pressed={density === item.value}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
