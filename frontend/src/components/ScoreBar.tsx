interface ScoreBarProps {
  label: string;
  value: number;
  color: string;
}

export default function ScoreBar({ label, value, color }: ScoreBarProps) {
  return (
    <div className="flex items-center gap-3 my-1">
      <span className="w-20 text-right text-xs text-gh-muted">{label}</span>
      <div className="flex-1 h-1.5 bg-gh-border rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${value * 100}%`, background: color }}
        />
      </div>
      <span className="w-12 text-xs text-gh-muted font-mono">{value.toFixed(3)}</span>
    </div>
  );
}
