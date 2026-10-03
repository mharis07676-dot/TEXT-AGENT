"use client";

import type { ConversationFilter } from "@/lib/types";

const FILTERS: Array<{ id: ConversationFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "unread", label: "Unread" },
  { id: "sms", label: "SMS" },
  { id: "whatsapp", label: "WhatsApp" },
  { id: "ai_active", label: "AI Active" },
  { id: "human_mode", label: "Human Mode" },
  { id: "closed", label: "Closed" },
];

export function ConversationFilters({
  value,
  onChange,
}: {
  value: ConversationFilter;
  onChange: (value: ConversationFilter) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="toolbar" aria-label="Conversation filters">
      {FILTERS.map((filter) => {
        const active = value === filter.id;
        return (
          <button
            key={filter.id}
            type="button"
            onClick={() => onChange(filter.id)}
            className={`rounded-full px-2.5 py-1 text-xs font-semibold transition ${
              active ? "bg-moss text-white" : "bg-mist text-moss/70 hover:bg-sand"
            }`}
            aria-pressed={active}
          >
            {filter.label}
          </button>
        );
      })}
    </div>
  );
}
