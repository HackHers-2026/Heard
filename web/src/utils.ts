export function formatDate(value?: string | null, includeTime = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    ...(date.getFullYear() !== new Date().getFullYear() ? { year: "numeric" as const } : {}),
    ...(includeTime ? { hour: "numeric" as const, minute: "2-digit" as const } : {}),
  }).format(date);
}

export function formatRelativeDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";

  const today = new Date();
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const difference = Math.round((todayStart - day) / 86_400_000);
  if (difference === 0) return "Today";
  if (difference === 1) return "Yesterday";
  return formatDate(value);
}

export function formatDuration(seconds?: number | null) {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return "—";
  const rounded = Math.round(seconds);
  const minutes = Math.floor(rounded / 60);
  const remaining = rounded % 60;
  return `${minutes}m ${remaining.toString().padStart(2, "0")}s`;
}

export function formatTimestamp(seconds?: number | null) {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const rounded = Math.floor(seconds);
  const minutes = Math.floor(rounded / 60);
  const remaining = rounded % 60;
  return `${minutes.toString().padStart(2, "0")}:${remaining.toString().padStart(2, "0")}`;
}

export function formatScore(value?: number | null) {
  return value == null || !Number.isFinite(value) ? "—" : Math.round(value).toString();
}

export function formatPercent(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "—";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)}%`;
}

export function initials(name?: string | null) {
  if (!name) return "H";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

export function readableError(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}
