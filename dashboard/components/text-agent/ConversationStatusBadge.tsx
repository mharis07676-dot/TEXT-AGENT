import { StatusBadge } from "@/components/StatusBadge";
import type { ConversationStatus } from "@/lib/types";

export function ConversationStatusBadge({ status }: { status: ConversationStatus }) {
  return <StatusBadge status={status} />;
}
