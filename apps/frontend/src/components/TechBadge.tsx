import type { ReactNode } from 'react';
import { Feather, Droplets, Thermometer, Leaf, Weight } from 'lucide-react';
import type { TechSpecs } from '../types/product';

interface TechBadgeListProps {
  specs: TechSpecs;
  size?: 'sm' | 'md';
}

const sizeClasses = {
  sm: 'text-xs px-2 py-1 gap-1',
  md: 'text-sm px-3 py-1.5 gap-1.5',
};

function Badge({ icon, label, size }: { icon: ReactNode; label: string; size: 'sm' | 'md' }) {
  return (
    <span
      className={`inline-flex items-center rounded-full bg-forest/8 text-forest-deep border border-forest/15 font-medium ${sizeClasses[size]}`}
    >
      {icon}
      {label}
    </span>
  );
}

export function TechBadgeList({ specs, size = 'sm' }: TechBadgeListProps) {
  const iconSize = size === 'sm' ? 12 : 14;
  const badges: Array<{ key: string; icon: ReactNode; label: string }> = [];

  if (specs.weightGrams !== undefined) {
    badges.push({
      key: 'weight',
      icon: <Feather size={iconSize} />,
      label:
        specs.weightGrams < 1000 ? `${specs.weightGrams} g` : `${(specs.weightGrams / 1000).toFixed(2)} kg`,
    });
  }
  if (specs.waterproofingMm !== undefined) {
    badges.push({
      key: 'waterproof',
      icon: <Droplets size={iconSize} />,
      label: `${specs.waterproofingMm.toLocaleString('fr-FR')} mm Schmerber`,
    });
  }
  if (specs.comfortTempC !== undefined) {
    badges.push({
      key: 'temp',
      icon: <Thermometer size={iconSize} />,
      label: `${specs.comfortTempC}°C confort`,
    });
  }
  if (specs.seasons !== undefined) {
    badges.push({ key: 'seasons', icon: <Leaf size={iconSize} />, label: `${specs.seasons} saisons` });
  }
  if (specs.capacityLiters !== undefined) {
    badges.push({ key: 'capacity', icon: <Weight size={iconSize} />, label: `${specs.capacityLiters} L` });
  }

  if (badges.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {badges.map((b) => (
        <Badge key={b.key} icon={b.icon} label={b.label} size={size} />
      ))}
    </div>
  );
}
