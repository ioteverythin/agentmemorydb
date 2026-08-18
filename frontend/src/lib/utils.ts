/** Merge class names, filtering falsy values */
export function cn(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(' ');
}

/** Format ISO date to locale string */
export function formatDate(date: string | null | undefined): string {
  if (!date) return '—';
  try {
    return new Date(date).toLocaleString();
  } catch {
    return date;
  }
}

/** Truncate a UUID for display */
export function formatId(id: string | null | undefined): string {
  if (!id) return '—';
  return id.length > 12 ? id.slice(0, 8) + '…' : id;
}

/** Map memory type to a hex color */
export function colorForType(type: string): string {
  const map: Record<string, string> = {
    semantic: '#58a6ff',
    episodic: '#bc8cff',
    procedural: '#3fb950',
    working: '#d29922',
  };
  return map[type] || '#484f58';
}

/** Map memory type to Tailwind classes for badges */
export function typeColorClass(type: string): string {
  const map: Record<string, string> = {
    semantic: 'bg-gh-accent-dim text-gh-accent',
    episodic: 'bg-gh-purple-dim text-gh-purple',
    procedural: 'bg-gh-green-dim text-gh-green',
    working: 'bg-gh-orange-dim text-gh-orange',
  };
  return map[type] || 'bg-gh-border text-gh-muted';
}

/**
 * Colour a memory's origin badge by how much the writer is trusted.
 *
 * Green = a human said it, blue = the system or agent produced it, orange =
 * it came from outside the conversation and deserves scepticism.
 */
export function originColorClass(origin?: string): string {
  const map: Record<string, string> = {
    operator: 'bg-gh-green-dim text-gh-green',
    user: 'bg-gh-green-dim text-gh-green',
    system: 'bg-gh-accent-dim text-gh-accent',
    agent_inference: 'bg-gh-accent-dim text-gh-accent',
    tool_output: 'bg-gh-orange-dim text-gh-orange',
    imported: 'bg-gh-purple-dim text-gh-purple',
    external_ingest: 'bg-gh-orange-dim text-gh-orange',
  };
  return map[origin ?? ''] || 'bg-gh-border text-gh-muted';
}

/** Colour a memory's status. Quarantined and disputed read as warnings. */
export function statusColorClass(status: string): string {
  const map: Record<string, string> = {
    active: 'text-gh-green',
    archived: 'text-gh-orange',
    quarantined: 'text-gh-orange',
    disputed: 'text-gh-orange',
    stale: 'text-gh-dim',
  };
  return map[status] || 'text-gh-red';
}

/** Generate a short unique ID */
export function generateId(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}
