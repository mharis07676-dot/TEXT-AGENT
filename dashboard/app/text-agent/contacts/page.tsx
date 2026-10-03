"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { ChannelBadge } from "@/components/text-agent/ChannelBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { displayName, formatDateTime, formatPhone } from "@/lib/format";
import type { Contact } from "@/lib/types";

function useDebouncedValue(value: string, delayMs: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export default function ContactsPage() {
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search, 300);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pageSize = 25;

  useEffect(() => {
    setPage(1);
  }, [debouncedSearch]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await api.getContacts({
          q: debouncedSearch,
          page,
          page_size: pageSize,
        });
        if (!cancelled) {
          setContacts(result.items);
          setTotal(result.total);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load contacts.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [debouncedSearch, page]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <AppShell title="Contacts" subtitle="Customers from SMS and WhatsApp conversations">
      <div className="space-y-4">
        <label className="block max-w-md">
          <span className="mb-1 block text-sm font-semibold text-moss/70">Search</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by name or phone"
            className="w-full rounded-md border border-moss/15 px-3 py-2 text-sm"
          />
        </label>

        {loading ? <LoadingState label="Loading contacts…" /> : null}
        {!loading && error ? <ErrorState message={error} onRetry={() => setPage((p) => p)} /> : null}
        {!loading && !error && contacts.length === 0 ? (
          <EmptyState
            title={search ? "No contacts match your search." : "No contacts yet."}
            description="Contacts are created automatically when customers message you."
          />
        ) : null}

        {!loading && !error && contacts.length > 0 ? (
          <div className="overflow-x-auto rounded-xl border border-moss/10 bg-white shadow-sm">
            <table className="min-w-[900px] w-full text-left text-sm">
              <thead className="bg-moss text-sand">
                <tr>
                  <th className="px-4 py-3 font-semibold">Name</th>
                  <th className="px-4 py-3 font-semibold">Phone</th>
                  <th className="px-4 py-3 font-semibold">Language</th>
                  <th className="px-4 py-3 font-semibold">Last channel</th>
                  <th className="px-4 py-3 font-semibold">Last activity</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Open</th>
                </tr>
              </thead>
              <tbody>
                {contacts.map((contact) => (
                  <tr key={contact.id} className="border-t border-moss/10 hover:bg-mist/70">
                    <td className="px-4 py-3 font-medium">
                      <Link href={`/text-agent/contacts/${contact.id}`} className="hover:underline">
                        {displayName(contact.name, contact.phone_number)}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{formatPhone(contact.phone_number)}</td>
                    <td className="px-4 py-3 capitalize">
                      {contact.preferred_language.replaceAll("_", " ")}
                    </td>
                    <td className="px-4 py-3">
                      {contact.last_channel ? (
                        <ChannelBadge channel={contact.last_channel} />
                      ) : (
                        "Not available"
                      )}
                    </td>
                    <td className="px-4 py-3">{formatDateTime(contact.last_activity_at)}</td>
                    <td className="px-4 py-3">
                      {contact.open_conversation_status ? (
                        <StatusBadge status={contact.open_conversation_status} />
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {contact.open_conversation_id ? (
                        <Link
                          href={`/text-agent/inbox?c=${contact.open_conversation_id}`}
                          className="font-semibold text-leaf hover:underline"
                        >
                          Conversation
                        </Link>
                      ) : (
                        <Link
                          href={`/text-agent/contacts/${contact.id}`}
                          className="font-semibold text-moss hover:underline"
                        >
                          Details
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {totalPages > 1 ? (
          <div className="flex items-center justify-between">
            <p className="text-sm text-moss/60">
              Page {page} of {totalPages} · {total} contacts
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                className="rounded-md border border-moss/15 px-3 py-1.5 text-sm font-semibold disabled:opacity-50"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                className="rounded-md border border-moss/15 px-3 py-1.5 text-sm font-semibold disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
