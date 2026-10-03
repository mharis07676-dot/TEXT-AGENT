"use client";

import { ChannelBadge } from "@/components/text-agent/ChannelBadge";
import { displayName, formatRelativeTime, maskPhone } from "@/lib/format";
import type { Conversation } from "@/lib/types";

export function ConversationListItem({
  conversation,
  selected,
  onSelect,
}: {
  conversation: Conversation;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const unread = conversation.unread_count > 0;

  return (
    <button
      type="button"
      onClick={() => onSelect(conversation.id)}
      className={`w-full border-b border-moss/10 px-3 py-3 text-left transition ${
        selected ? "bg-sand" : "bg-white hover:bg-mist/80"
      }`}
      aria-current={selected ? "true" : undefined}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className={`truncate text-sm ${unread ? "font-bold text-ink" : "font-semibold text-ink"}`}>
            {displayName(conversation.contact_name, conversation.contact_phone)}
          </p>
          <p className="mt-0.5 truncate text-xs text-moss/55">{maskPhone(conversation.contact_phone)}</p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="text-[11px] text-moss/50">
            {formatRelativeTime(conversation.latest_message_at ?? conversation.last_message_at)}
          </span>
          {unread ? (
            <span className="rounded-full bg-signal px-1.5 py-0.5 text-[10px] font-bold text-white">
              {conversation.unread_count}
            </span>
          ) : null}
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <p className="truncate text-xs text-moss/65">
          {conversation.latest_message_preview || "No messages yet"}
        </p>
        <ChannelBadge channel={conversation.channel} />
      </div>
      <div className="mt-2 flex items-center gap-2 text-[11px] text-moss/55">
        <span className="capitalize">{conversation.status}</span>
        <span aria-hidden="true">·</span>
        <span>{conversation.ai_enabled ? "AI Active" : "Human Mode"}</span>
      </div>
    </button>
  );
}
