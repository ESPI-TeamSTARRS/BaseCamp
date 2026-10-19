import { Truck, ShieldCheck, RotateCcw } from 'lucide-react';

const items = [
  { icon: Truck, label: 'Expédition en 24/48h' },
  { icon: ShieldCheck, label: 'Garantie aventure & déchirure' },
  { icon: RotateCcw, label: 'Retours gratuits sous 30 jours' },
];

export function ReassuranceBar() {
  return (
    <div className="border-y border-granite/10 bg-sand">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-6 px-4 py-3 text-sm font-medium text-forest-deep sm:justify-between">
        {items.map(({ icon: Icon, label }) => (
          <div key={label} className="flex items-center gap-2">
            <Icon size={16} className="text-bivouac" />
            <span>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
