"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ChatHeader } from "@/components/text-agent/ChatHeader";
import { ConversationList } from "@/components/text-agent/ConversationList";
import { CustomerDetails } from "@/components/text-agent/CustomerDetails";
import { MessageComposer } from "@/components/text-agent/MessageComposer";
import { MessageList } from "@/components/text-agent/MessageList";
import { api } from "@/lib/api";
import type { Conversation, ConversationFilter, Message } from "@/lib/types";

const STREAM_TEMP_ID = "temp-stream";
const DELTA_FLUSH_MS = 50;

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export function InboxWorkspace({ initialConversationId = null }: { initialConversationId?: string | null }) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<ConversationFilter>("all");
  const debouncedSearch = useDebouncedValue(search, 300);

  const [selectedId, setSelectedId] = useState<string | null>(initialConversationId);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [modeBusy, setModeBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<"close" | "archive" | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [mobileView, setMobileView] = useState<"list" | "chat" | "details">("list");
  const [aiTyping, setAiTyping] = useState(false);

  const streamBufferRef = useRef("");
  const flushTimerRef = useRef<number | null>(null);
  const selectedIdRef = useRef<string | null>(selectedId);
  selectedIdRef.current = selectedId;

  const selected = useMemo(
    () => conversations.find((item) => item.id === selectedId) ?? conversation,
    [conversations, selectedId, conversation],
  );

  const loadConversations = useCallback(async () => {
    setListLoading(true);
    setListError(null);
    try {
      const result = await api.getConversations({
        q: debouncedSearch,
        filter,
        page_size: 100,
      });
      setConversations(result.items);
    } catch (error) {
      setListError(error instanceof Error ? error.message : "Unable to load conversations.");
    } finally {
      setListLoading(false);
    }
  }, [debouncedSearch, filter]);

  const loadThread = useCallback(async (id: string) => {
    setMessagesLoading(true);
    setSendError(null);
    setAiTyping(false);
    try {
      const [conv, messageResult] = await Promise.all([
        api.getConversation(id),
        api.getMessages(id, { limit: 50 }),
      ]);
      setConversation(conv);
      setMessages(messageResult.items);
      setHasMore(messageResult.has_more);
      setConversations((current) =>
        current.map((item) => (item.id === id ? { ...item, ...conv, unread_count: 0 } : item)),
      );
    } catch (error) {
      setToast(error instanceof Error ? error.message : "Unable to load conversation.");
    } finally {
      setMessagesLoading(false);
    }
  }, []);

  const flushStreamBuffer = useCallback(() => {
    const text = streamBufferRef.current;
    setMessages((current) => {
      const existing = current.find((item) => item.id === STREAM_TEMP_ID);
      if (!existing) {
        if (!selectedIdRef.current) return current;
        return [
          ...current.filter((item) => item.id !== STREAM_TEMP_ID),
          {
            id: STREAM_TEMP_ID,
            conversation_id: selectedIdRef.current,
            role: "assistant",
            direction: "outbound",
            channel: selected?.channel ?? "sms",
            body: text,
            streaming: true,
            created_at: new Date().toISOString(),
          },
        ];
      }
      return current.map((item) =>
        item.id === STREAM_TEMP_ID ? { ...item, body: text, streaming: true } : item,
      );
    });
  }, [selected?.channel]);

  const scheduleFlush = useCallback(() => {
    if (flushTimerRef.current != null) return;
    flushTimerRef.current = window.setTimeout(() => {
      flushTimerRef.current = null;
      flushStreamBuffer();
    }, DELTA_FLUSH_MS);
  }, [flushStreamBuffer]);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    if (!selectedId) {
      setConversation(null);
      setMessages([]);
      setAiTyping(false);
      return;
    }
    void loadThread(selectedId);
  }, [selectedId, loadThread]);

  // SSE for live inbound + AI streaming; light polling as a safety net.
  useEffect(() => {
    if (!selectedId) return;

    let source: EventSource | null = null;
    try {
      source = api.openConversationStream(selectedId, {
        onEvent: (event, data) => {
          if (selectedIdRef.current !== selectedId) return;

          if (event === "inbound") {
            const message = data.message as Message | undefined;
            if (!message?.id) return;
            setMessages((current) => {
              if (current.some((item) => item.id === message.id)) return current;
              return [...current.filter((item) => item.id !== STREAM_TEMP_ID || item.streaming), message];
            });
            void loadConversations();
            return;
          }

          if (event === "start") {
            streamBufferRef.current = "";
            setAiTyping(true);
            setMessages((current) => [
              ...current.filter((item) => item.id !== STREAM_TEMP_ID),
              {
                id: STREAM_TEMP_ID,
                conversation_id: selectedId,
                role: "assistant",
                direction: "outbound",
                channel: selected?.channel ?? "sms",
                body: "",
                streaming: true,
                created_at: new Date().toISOString(),
              },
            ]);
            return;
          }

          if (event === "delta") {
            const text = typeof data.text === "string" ? data.text : "";
            if (!text) return;
            streamBufferRef.current += text;
            scheduleFlush();
            return;
          }

          if (event === "done") {
            if (flushTimerRef.current != null) {
              window.clearTimeout(flushTimerRef.current);
              flushTimerRef.current = null;
            }
            const messageId = typeof data.message_id === "string" ? data.message_id : null;
            const body =
              typeof data.body === "string" ? data.body : streamBufferRef.current;
            streamBufferRef.current = "";
            setAiTyping(false);
            setMessages((current) => {
              const withoutTemp = current.filter((item) => item.id !== STREAM_TEMP_ID);
              if (!messageId) return withoutTemp;
              if (withoutTemp.some((item) => item.id === messageId)) return withoutTemp;
              return [
                ...withoutTemp,
                {
                  id: messageId,
                  conversation_id: selectedId,
                  role: "assistant",
                  direction: "outbound",
                  channel: selected?.channel ?? "sms",
                  body,
                  provider_status: "queued",
                  created_at: new Date().toISOString(),
                },
              ];
            });
            void loadThread(selectedId);
            void loadConversations();
            return;
          }

          if (event === "error") {
            if (flushTimerRef.current != null) {
              window.clearTimeout(flushTimerRef.current);
              flushTimerRef.current = null;
            }
            streamBufferRef.current = "";
            setAiTyping(false);
            setMessages((current) =>
              current.map((item) =>
                item.id === STREAM_TEMP_ID
                  ? {
                      ...item,
                      body: item.body || "AI response failed.",
                      streaming: false,
                      failed: true,
                      provider_status: "failed",
                    }
                  : item,
              ),
            );
            setToast("AI response failed.");
          }
        },
      });
    } catch {
      // Fall back to polling only.
    }

    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const [convList, messageResult, conv] = await Promise.all([
            api.getConversations({ q: debouncedSearch, filter, page_size: 100 }),
            api.getMessages(selectedId, { limit: 50 }),
            api.getConversation(selectedId),
          ]);
          setConversations(convList.items);
          setConversation(conv);
          setMessages((current) => {
            const streaming = current.find((item) => item.id === STREAM_TEMP_ID && item.streaming);
            const optimistic = current.filter((item) => item.optimistic);
            const serverIds = new Set(messageResult.items.map((item) => item.id));
            const pending = optimistic.filter((item) => !serverIds.has(item.id));
            const merged = [...messageResult.items, ...pending];
            return streaming ? [...merged.filter((item) => item.id !== STREAM_TEMP_ID), streaming] : merged;
          });
          setHasMore(messageResult.has_more);
        } catch {
          // Keep the current view on poll failures.
        }
      })();
    }, 12000);

    return () => {
      source?.close();
      window.clearInterval(timer);
      if (flushTimerRef.current != null) {
        window.clearTimeout(flushTimerRef.current);
        flushTimerRef.current = null;
      }
      streamBufferRef.current = "";
      setAiTyping(false);
    };
  }, [selectedId, debouncedSearch, filter, loadConversations, loadThread, scheduleFlush, selected?.channel]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  async function handleSelect(id: string) {
    setSelectedId(id);
    setMobileView("chat");
  }

  async function handleSend(body: string) {
    if (!selectedId || !selected) return;
    const tempId = `temp-${Date.now()}`;
    const optimistic: Message = {
      id: tempId,
      conversation_id: selectedId,
      role: "human",
      direction: "outbound",
      channel: selected.channel,
      body,
      provider_status: "sending",
      created_at: new Date().toISOString(),
      optimistic: true,
    };
    setMessages((current) => [...current, optimistic]);
    setSending(true);
    setSendError(null);
    try {
      const saved = await api.sendMessage(selectedId, body);
      setMessages((current) => current.map((item) => (item.id === tempId ? saved : item)));
      await loadConversations();
    } catch (error) {
      setMessages((current) =>
        current.map((item) =>
          item.id === tempId
            ? { ...item, optimistic: false, failed: true, provider_status: "failed" }
            : item,
        ),
      );
      setSendError(error instanceof Error ? error.message : "Failed to send message.");
    } finally {
      setSending(false);
    }
  }

  async function handleAiMode(enabled: boolean) {
    if (!selectedId) return;
    setModeBusy(true);
    try {
      await api.setAiMode(selectedId, enabled);
      setConversation((current) => (current ? { ...current, ai_enabled: enabled } : current));
      setConversations((current) =>
        current.map((item) => (item.id === selectedId ? { ...item, ai_enabled: enabled } : item)),
      );
      setToast(
        enabled
          ? "AI automatic replies are enabled."
          : "AI replies are paused for this conversation.",
      );
    } catch (error) {
      setToast(error instanceof Error ? error.message : "Unable to update AI mode.");
    } finally {
      setModeBusy(false);
    }
  }

  async function applyStatus(status: "closed" | "active" | "archived") {
    if (!selectedId) return;
    setConfirmBusy(true);
    try {
      const updated = await api.updateConversation(selectedId, { status });
      setConversation(updated);
      setConversations((current) =>
        current.map((item) => (item.id === selectedId ? { ...item, ...updated } : item)),
      );
      setToast(`Conversation marked ${status}.`);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "Unable to update conversation.");
    } finally {
      setConfirmBusy(false);
      setConfirmAction(null);
    }
  }

  async function loadOlder() {
    if (!selectedId || messages.length === 0) return;
    const oldest = messages[0]?.created_at;
    if (!oldest) return;
    setLoadingOlder(true);
    try {
      const older = await api.getMessages(selectedId, { limit: 50, before: oldest });
      setMessages((current) => {
        const existing = new Set(current.map((item) => item.id));
        const merged = older.items.filter((item) => !existing.has(item.id));
        return [...merged, ...current];
      });
      setHasMore(older.has_more);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "Unable to load older messages.");
    } finally {
      setLoadingOlder(false);
    }
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      {toast ? (
        <div className="absolute right-4 top-4 z-20 rounded-md bg-moss px-3 py-2 text-sm text-white shadow">
          {toast}
        </div>
      ) : null}

      <div className="grid min-h-[calc(100vh-7rem)] flex-1 grid-cols-1 md:grid-cols-[320px_minmax(0,1fr)] xl:grid-cols-[320px_minmax(0,1fr)_300px]">
        <div className={`${mobileView === "list" ? "block" : "hidden"} min-h-0 md:block`}>
          <ConversationList
            conversations={conversations}
            selectedId={selectedId}
            loading={listLoading}
            error={listError}
            search={search}
            filter={filter}
            onSearchChange={setSearch}
            onFilterChange={setFilter}
            onSelect={handleSelect}
            onRetry={() => void loadConversations()}
          />
        </div>

        <section
          className={`${mobileView === "chat" ? "flex" : "hidden"} min-h-0 flex-col bg-mist/30 md:flex`}
        >
          {!selected ? (
            <div className="flex h-full items-center justify-center p-6">
              <EmptyState
                title="Select a conversation to start."
                description="Choose a thread from the inbox to view messages and reply."
              />
            </div>
          ) : (
            <>
              <div className="border-b border-moss/10 bg-white px-3 py-2 md:hidden">
                <button
                  type="button"
                  onClick={() => setMobileView("list")}
                  className="text-sm font-semibold text-moss"
                >
                  ← Back to inbox
                </button>
              </div>
              <ChatHeader
                conversation={selected}
                modeBusy={modeBusy}
                onAiModeChange={(enabled) => void handleAiMode(enabled)}
                onClose={() => setConfirmAction("close")}
                onReopen={() => void applyStatus("active")}
                onArchive={() => setConfirmAction("archive")}
                onShowDetails={() => setMobileView("details")}
              />
              <div className="min-h-0 flex-1">
                <MessageList
                  messages={messages}
                  loading={messagesLoading}
                  hasMore={hasMore}
                  loadingOlder={loadingOlder}
                  onLoadOlder={() => void loadOlder()}
                  aiTyping={aiTyping}
                />
              </div>
              <MessageComposer
                conversation={selected}
                sending={sending}
                onSend={handleSend}
                error={sendError}
              />
            </>
          )}
        </section>

        <div
          className={`${
            mobileView === "details" ? "fixed inset-0 z-30 bg-white" : "hidden"
          } xl:static xl:block`}
        >
          <CustomerDetails
            conversation={selected}
            onClosePanel={() => setMobileView("chat")}
          />
        </div>
      </div>

      <ConfirmDialog
        open={confirmAction !== null}
        title={confirmAction === "archive" ? "Archive conversation?" : "Close conversation?"}
        description={
          confirmAction === "archive"
            ? "Archived conversations stay available in history but leave the active inbox."
            : "Closed conversations stop the active thread. You can reopen later."
        }
        confirmLabel={confirmAction === "archive" ? "Archive" : "Close"}
        busy={confirmBusy}
        onCancel={() => setConfirmAction(null)}
        onConfirm={() => void applyStatus(confirmAction === "archive" ? "archived" : "closed")}
      />
    </div>
  );
}
