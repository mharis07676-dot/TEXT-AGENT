"use client";

import { AIModeToggle } from "@/components/text-agent/AIModeToggle";
import { ChannelBadge } from "@/components/text-agent/ChannelBadge";
import { ConversationStatusBadge } from "@/components/text-agent/ConversationStatusBadge";
import { displayName, formatPhone } from "@/lib/format";
import type { Conversation } from "@/lib/types";

export function ChatHeader({
  conversation,
  modeBusy,
  onAiModeChange,
  onClose,
  onReopen,
  onArchive,
  onShowDetails,
}: {
  conversation: Conversation;
  modeBusy?: boolean;
  onAiModeChange: (enabled: boolean) => void;
  onClose: () => void;
  onReopen: () => void;
  onArchive: () => void;
  onShowDetails?: () => void;
}) {
  return (
    <header className="border-b border-moss/10 bg-white px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate font-display text-xl font-semibold text-ink">
              {displayName(conversation.contact_name, conversation.contact_phone)}
            </h3>
            <ChannelBadge channel={conversation.channel} />
            <ConversationStatusBadge status={conversation.status} />
          </div>
          <p className="mt-1 text-sm text-moss/60">{formatPhone(conversation.contact_phone)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {onShowDetails ? (
            <button
              type="button"
              onClick={onShowDetails}
              className="rounded-md border border-moss/15 px-3 py-1.5 text-xs font-semibold text-ink lg:hidden"
            >
              Details
            </button>
          ) : null}
          <AIModeToggle
            aiEnabled={conversation.ai_enabled}
            busy={modeBusy}
            onChange={onAiModeChange}
          />
          {conversation.status === "active" ? (
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-moss/15 px-3 py-1.5 text-xs font-semibold text-ink"
            >
              Close
            </button>
          ) : (
            <button
              type="button"
              onClick={onReopen}
              className="rounded-md border border-moss/15 px-3 py-1.5 text-xs font-semibold text-ink"
            >
              Reopen
            </button>
          )}
          {conversation.status !== "archived" ? (
            <button
              type="button"
              onClick={onArchive}
              className="rounded-md border border-moss/15 px-3 py-1.5 text-xs font-semibold text-ink"
            >
              Archive
            </button>
          ) : null}
        </div>
      </div>
      <p
        className={`mt-3 rounded-md px-3 py-2 text-xs ${
          conversation.ai_enabled
            ? "bg-emerald-50 text-emerald-800"
            : "bg-amber-50 text-amber-800"
        }`}
        role="status"
      >
        {conversation.ai_enabled
          ? "AI automatic replies are enabled."
          : "AI replies are paused for this conversation."}
      </p>
    </header>
  );
}
