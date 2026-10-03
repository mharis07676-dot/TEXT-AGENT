"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/AppShell";
import { DataView, useAsyncData } from "@/components/useAsyncData";
import { ChannelBadge } from "@/components/text-agent/ChannelBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { displayName, formatDateTime, formatPhone } from "@/lib/format";

export default function ContactDetailPage() {
  const params = useParams<{ id: string }>();
  const contactId = params.id;

  const { data, error, loading, reload } = useAsyncData(async () => {
    const [contact, conversations] = await Promise.all([
      api.getContact(contactId),
      api.getContactConversations(contactId),
    ]);
    return { contact, conversations };
  }, [contactId]);

  return (
    <AppShell title="Contact details" subtitle="Customer profile and conversation history">
      <DataView
        loading={loading}
        error={error}
        data={data}
        emptyTitle="Contact not found."
        onRetry={reload}
      >
        {(view) => (
          <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
            <section className="rounded-xl border border-moss/10 bg-white p-5 shadow-sm">
              <h3 className="font-display text-xl font-semibold">Basic info</h3>
              <dl className="mt-4 space-y-3 text-sm">
                <div>
                  <dt className="text-moss/55">Name</dt>
                  <dd className="font-medium">
                    {displayName(view.contact.name, view.contact.phone_number)}
                  </dd>
                </div>
                <div>
                  <dt className="text-moss/55">Phone</dt>
                  <dd className="font-medium">{formatPhone(view.contact.phone_number)}</dd>
                </div>
                <div>
                  <dt className="text-moss/55">Preferred language</dt>
                  <dd className="font-medium capitalize">
                    {view.contact.preferred_language.replaceAll("_", " ")}
                  </dd>
                </div>
                <div>
                  <dt className="text-moss/55">Created</dt>
                  <dd className="font-medium">{formatDateTime(view.contact.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-moss/55">Lead status</dt>
                  <dd className="font-medium">
                    {view.contact.metadata?.lead_status || "Not available"}
                  </dd>
                </div>
                <div>
                  <dt className="text-moss/55">Tags</dt>
                  <dd className="font-medium">
                    {view.contact.metadata?.tags?.length
                      ? view.contact.metadata.tags.join(", ")
                      : "Not available"}
                  </dd>
                </div>
                <div>
                  <dt className="text-moss/55">Notes</dt>
                  <dd className="font-medium">{view.contact.metadata?.notes || "Not available"}</dd>
                </div>
              </dl>
            </section>

            <section className="rounded-xl border border-moss/10 bg-white p-5 shadow-sm">
              <h3 className="font-display text-xl font-semibold">Conversation history</h3>
              {view.conversations.length === 0 ? (
                <p className="mt-4 text-sm text-moss/60">No conversations for this contact.</p>
              ) : (
                <ul className="mt-4 divide-y divide-moss/10">
                  {view.conversations.map((conversation) => (
                    <li key={conversation.id} className="flex items-center justify-between gap-3 py-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <ChannelBadge channel={conversation.channel} />
                          <StatusBadge status={conversation.status} />
                          <span className="text-xs text-moss/55">
                            {conversation.ai_enabled ? "AI Active" : "Human Mode"}
                          </span>
                        </div>
                        <p className="mt-1 truncate text-sm text-moss/70">
                          {conversation.latest_message_preview || "No messages yet"}
                        </p>
                        <p className="mt-1 text-xs text-moss/50">
                          Last active{" "}
                          {formatDateTime(
                            conversation.latest_message_at ?? conversation.last_message_at,
                          )}
                        </p>
                      </div>
                      <Link
                        href={`/text-agent/inbox?c=${conversation.id}`}
                        className="shrink-0 text-sm font-semibold text-leaf hover:underline"
                      >
                        Open
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}
      </DataView>
    </AppShell>
  );
}
