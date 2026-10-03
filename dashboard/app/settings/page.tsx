"use client";

import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/components/AuthProvider";

export default function SettingsPage() {
  const { user } = useAuth();

  return (
    <AppShell title="Account" subtitle="Signed-in user and organization preferences">
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-moss/10 bg-white p-6 shadow-sm">
          <h3 className="font-display text-xl font-semibold">Account / Profile</h3>
          <dl className="mt-4 space-y-3 text-sm">
            <div>
              <dt className="text-moss/55">Name</dt>
              <dd className="font-medium">{user?.full_name ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-moss/55">Email</dt>
              <dd className="font-medium">{user?.email ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-moss/55">Role</dt>
              <dd className="font-medium capitalize">{user?.role ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-moss/55">Tenant ID</dt>
              <dd className="break-all font-medium">{user?.tenant_id ?? "—"}</dd>
            </div>
          </dl>
        </section>

        <section className="rounded-xl border border-moss/10 bg-white p-6 shadow-sm">
          <h3 className="font-display text-xl font-semibold">Organization</h3>
          <p className="mt-3 text-sm text-moss/65">
            Channel integration status lives under Text Agent → Settings. Secret credentials are never
            exposed in the dashboard.
          </p>
        </section>
      </div>
    </AppShell>
  );
}
