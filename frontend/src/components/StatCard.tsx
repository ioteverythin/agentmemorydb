interface StatCardProps {
  icon: string;
  value: string | number;
  label: string;
  color?: string;
}

export default function StatCard({ icon, value, label, color }: StatCardProps) {
  return (
    <div className="bg-gh-canvas border border-gh-border rounded-lg p-5 text-center">
      <div className="text-2xl mb-1">{icon}</div>
      <div className="text-2xl font-bold" style={{ color: color || '#58a6ff' }}>
        {value}
      </div>
      <div className="text-xs text-gh-muted mt-1">{label}</div>
    </div>
  );
}
