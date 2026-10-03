"use client";

export function AIModeToggle({
  aiEnabled,
  busy,
  onChange,
}: {
  aiEnabled: boolean;
  busy?: boolean;
  onChange: (enabled: boolean) => void;
}) {
  return (
    <div className="inline-flex rounded-md border border-moss/15 bg-mist p-0.5" role="group" aria-label="AI mode">
      <button
        type="button"
        disabled={busy}
        aria-pressed={aiEnabled}
        onClick={() => onChange(true)}
        className={`rounded px-3 py-1.5 text-xs font-semibold transition disabled:opacity-60 ${
          aiEnabled ? "bg-leaf text-white" : "text-moss/70 hover:bg-white"
        }`}
      >
        AI
      </button>
      <button
        type="button"
        disabled={busy}
        aria-pressed={!aiEnabled}
        onClick={() => onChange(false)}
        className={`rounded px-3 py-1.5 text-xs font-semibold transition disabled:opacity-60 ${
          !aiEnabled ? "bg-signal text-white" : "text-moss/70 hover:bg-white"
        }`}
      >
        Human
      </button>
    </div>
  );
}
