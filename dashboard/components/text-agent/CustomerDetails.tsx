"use client";

import { ChannelBadge } from "@/components/text-agent/ChannelBadge";
import { ConversationStatusBadge } from "@/components/text-agent/ConversationStatusBadge";
import { displayName, formatDateTime, formatPhone } from "@/lib/format";
import type { Conversation } from "@/lib/types";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-moss/50">{label}</dt>
      <dd className="mt-1 text-sm text-ink">{value}</dd>
    </div>
  );
}

export function CustomerDetails({
  conversation,
  onClosePanel,
}: {
  conversation: Conversation | null;
  onClosePanel?: () => void;
}) {
  if (!conversation) {
    return (
      <aside className="hidden h-full border-l border-moss/10 bg-white p-4 xl:block">
        <p className="text-sm text-moss/60">Select a conversation to view customer details.</p>
      </aside>
    );
  }

  const meta = conversation.metadata ?? {};
  const tags = Array.isArray(meta.tags) ? (meta.tags as string[]) : [];
  const notes = typeof meta.notes === "string" ? meta.notes : null;
  const leadStatus = typeof meta.lead_status === "string" ? meta.lead_status : null;

  return (
    <aside className="h-full overflow-y-auto border-l border-moss/10 bg-white p-4">
      <div className="mb-4 flex items-start justify-between gap-2">
        <div>
          <h3 className="font-display text-lg font-semibold text-ink">Customer Info</h3>
          <p className="mt-1 text-sm text-moss/60">Conversation details</p>
        </div>
        {onClosePanel ? (
          <button
            type="button"
            onClick={onClosePanel}
            className="rounded-md border border-moss/15 px-2 py-1 text-xs font-semibold xl:hidden"
            aria-label="Close details"
          >
            Close
          </button>
        ) : null}
      </div>

      <dl className="space-y-4">
        <Field
          label="Name"
          value={displayName(conversation.contact_name, conversation.contact_phone)}
        />
        <Field label="Phone" value={formatPhone(conversation.contact_phone)} />
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-moss/50">Channel</dt>
          <dd className="mt-1">
            <ChannelBadge channel={conversation.channel} />
          </dd>
        </div>
        <Field
          label="Preferred language"
          value={conversation.preferred_language?.replaceAll("_", " ") ?? "Not available"}
        />
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-moss/50">Status</dt>
          <dd className="mt-1">
            <ConversationStatusBadge status={conversation.status} />
          </dd>
        </div>
        <Field label="AI status" value={conversation.ai_enabled ? "AI Enabled" : "Human Mode"} />
        <Field label="First contacted" value={formatDateTime(conversation.created_at)} />
        <Field
          label="Last active"
          value={formatDateTime(conversation.latest_message_at ?? conversation.last_message_at)}
        />
        <Field label="Lead status" value={leadStatus || "Not available"} />
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-moss/50">Tags</dt>
          <dd className="mt-1 text-sm text-ink">
            {tags.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {tags.map((tag) => (
                  <span key={tag} className="rounded-full bg-mist px-2 py-0.5 text-xs font-semibold">
                    {tag}
                  </span>
                ))}
              </div>
            ) : (
              "Not available"
            )}
          </dd>
        </div>
        <Field label="Notes" value={notes || "Not available"} />
      </dl>
    </aside>
  );
}
