import { clearToken, getToken } from "./auth";
import type {
  Contact,
  Conversation,
  ConversationFilter,
  LoginPayload,
  Message,
  MessageList,
  MessagingAnalytics,
  MessagingHealth,
  MessagingStats,
  Paginated,
  TokenResponse,
  User,
} from "./types";
import { ApiError } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";

async function request<T>(path: string, init?: RequestInit, auth = true): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (auth) {
    const token = getToken();
    if (!token) {
      throw new ApiError(401, "Not authenticated");
    }
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new ApiError(401, "Unauthorized");
  }

  if (!res.ok) {
    let detail = await res.text();
    try {
      const parsed = JSON.parse(detail) as { detail?: string };
      if (parsed.detail) detail = parsed.detail;
    } catch {
      // keep raw text
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

function toQuery(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    search.set(key, String(value));
  });
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  login(payload: LoginPayload) {
    return request<TokenResponse>(
      "/auth/login",
      { method: "POST", body: JSON.stringify(payload) },
      false,
    );
  },

  me() {
    return request<User>("/auth/me");
  },

  getMessagingHealth() {
    return request<MessagingHealth>("/messaging/health", undefined, false);
  },

  getMessagingStats() {
    return request<MessagingStats>("/messaging/stats");
  },

  getMessagingAnalytics() {
    return request<MessagingAnalytics>("/messaging/analytics");
  },

  getConversations(params: {
    q?: string;
    filter?: ConversationFilter;
    page?: number;
    page_size?: number;
  } = {}) {
    return request<Paginated<Conversation>>(
      `/messaging/conversations${toQuery({
        q: params.q,
        filter: params.filter,
        page: params.page,
        page_size: params.page_size,
      })}`,
    );
  },

  getConversation(id: string) {
    return request<Conversation>(`/messaging/conversations/${id}`);
  },

  updateConversation(
    id: string,
    payload: { status?: string; ai_enabled?: boolean; name?: string },
  ) {
    return request<Conversation>(`/messaging/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  setAiMode(id: string, aiEnabled: boolean) {
    return request<{ ok: boolean; conversation_id: string; ai_enabled: boolean }>(
      `/messaging/conversations/${id}/ai-mode`,
      {
        method: "POST",
        body: JSON.stringify({ ai_enabled: aiEnabled }),
      },
    );
  },

  getMessages(conversationId: string, params: { limit?: number; before?: string } = {}) {
    return request<MessageList>(
      `/messaging/conversations/${conversationId}/messages${toQuery({
        limit: params.limit,
        before: params.before,
      })}`,
    );
  },

  sendMessage(conversationId: string, body: string) {
    return request<Message>(`/messaging/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ body }),
    });
  },

  getContacts(params: { q?: string; page?: number; page_size?: number } = {}) {
    return request<Paginated<Contact>>(
      `/messaging/contacts${toQuery({
        q: params.q,
        page: params.page,
        page_size: params.page_size,
      })}`,
    );
  },

  getContact(id: string) {
    return request<Contact>(`/messaging/contacts/${id}`);
  },

  getContactConversations(id: string) {
    return request<Conversation[]>(`/messaging/contacts/${id}/conversations`);
  },

  updateContact(
    id: string,
    payload: { name?: string; preferred_language?: string; notes?: string; tags?: string[] },
  ) {
    return request<Contact>(`/messaging/contacts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
};

export { API_URL };
