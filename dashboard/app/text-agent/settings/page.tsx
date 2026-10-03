"use client";

import { AppShell } from "@/components/AppShell";
import { DataView, useAsyncData } from "@/components/useAsyncData";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";

function configLabel(ok: boolean): string {
  return ok ? "Configured" : "Not configured";
}

export default function TextAgentSettingsPage() {
  const { data, error, loading, reload } = useAsyncData(() => api.getMessagingHealth(), []);

  return (
    <AppShell title="Text Agent Settings" subtitle="Integration status and channel configuration">
      <DataView
        loading={loading}
        error={error}
        data={data}
        emptyTitle="Settings unavailable."
        onRetry={reload}
      >
        {(health) => (
          <div className="grid gap-6 lg:grid-cols-2">
            <section className="rounded-xl border border-moss/10 bg-white p-6 shadow-sm">
              <h3 className="font-display text-xl font-semibold">Integrations</h3>
              <p className="mt-2 text-sm text-moss/65">
                Secret values are never shown. Status is read from a safe health endpoint.
              </p>
              <dl className="mt-5 space-y-4 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <dt className="font-medium">Twilio</dt>
                  <dd>
                    <StatusBadge
                      status={health.twilio_configured ? "Connected" : "Not configured"}
                    />
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="font-medium">SMS</dt>
                  <dd>
                    <StatusBadge status={configLabel(health.sms_configured)} />
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="font-medium">WhatsApp</dt>
                  <dd>
                    <StatusBadge status={configLabel(health.whatsapp_configured)} />
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="font-medium">OpenAI</dt>
                  <dd>
                    <StatusBadge status={configLabel(health.openai_configured)} />
                  </dd>
                </div>
              </dl>
            </section>

            <section className="rounded-xl border border-moss/10 bg-white p-6 shadow-sm">
              <h3 className="font-display text-xl font-semibold">AI behavior</h3>
              <p className="mt-3 text-sm text-moss/65">
                New conversations start with AI replies enabled. Use the inbox AI / Human toggle to
                pause automatic replies for a specific conversation.
              </p>
              <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-moss/70">
                <li>AI Mode: OpenAI may auto-reply to inbound messages.</li>
                <li>Human Mode: inbound messages are stored; staff reply manually.</li>
                <li>Manual dashboard sends are stored with role = human.</li>
              </ul>
            </section>
          </div>
        )}
      </DataView>
    </AppShell>
  );
}
