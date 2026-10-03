"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AppShell } from "@/components/AppShell";
import { LoadingState } from "@/components/LoadingState";
import { InboxWorkspace } from "@/components/text-agent/InboxWorkspace";

function InboxContent() {
  const params = useSearchParams();
  const conversationId = params.get("c");

  return (
    <AppShell
      title="Inbox"
      subtitle="Shared SMS + WhatsApp conversations"
      dense
    >
      <InboxWorkspace initialConversationId={conversationId} />
    </AppShell>
  );
}

export default function InboxPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen p-6">
          <LoadingState label="Loading inbox…" />
        </div>
      }
    >
      <InboxContent />
    </Suspense>
  );
}
