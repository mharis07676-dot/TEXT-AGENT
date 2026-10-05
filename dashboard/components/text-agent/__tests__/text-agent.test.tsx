import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChannelBadge } from "@/components/text-agent/ChannelBadge";
import { ConversationFilters } from "@/components/text-agent/ConversationFilters";
import { ConversationList } from "@/components/text-agent/ConversationList";
import { MessageBubble } from "@/components/text-agent/MessageBubble";
import { MessageComposer } from "@/components/text-agent/MessageComposer";
import { AIModeToggle } from "@/components/text-agent/AIModeToggle";
import { channelLabel, senderLabel } from "@/lib/format";
import type { Conversation, Message } from "@/lib/types";

const baseConversation: Conversation = {
  id: "c1",
  contact_id: "p1",
  channel: "sms",
  status: "active",
  ai_enabled: true,
  unread_count: 0,
  contact_name: "Haris",
  contact_phone: "+923001234567",
  latest_message_preview: "Hello",
  latest_message_at: new Date().toISOString(),
};

describe("text agent UI helpers", () => {
  it("labels channels correctly", () => {
    expect(channelLabel("sms")).toBe("SMS");
    expect(channelLabel("whatsapp")).toBe("WhatsApp");
  });

  it("labels senders correctly", () => {
    expect(senderLabel("user")).toBe("Customer");
    expect(senderLabel("assistant")).toBe("AI");
    expect(senderLabel("human")).toBe("You");
  });
});

describe("ChannelBadge", () => {
  it("renders SMS badge", () => {
    render(<ChannelBadge channel="sms" />);
    expect(screen.getByLabelText("Channel SMS")).toBeInTheDocument();
  });

  it("renders WhatsApp badge", () => {
    render(<ChannelBadge channel="whatsapp" />);
    expect(screen.getByLabelText("Channel WhatsApp")).toBeInTheDocument();
  });
});

describe("ConversationList", () => {
  it("renders conversation rows and empty search state", () => {
    const onSelect = vi.fn();
    render(
      <ConversationList
        conversations={[baseConversation]}
        selectedId={null}
        loading={false}
        error={null}
        search=""
        filter="all"
        onSearchChange={() => undefined}
        onFilterChange={() => undefined}
        onSelect={onSelect}
        onRetry={() => undefined}
      />,
    );
    expect(screen.getByText("Haris")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Haris"));
    expect(onSelect).toHaveBeenCalledWith("c1");
  });

  it("shows empty conversation state", () => {
    render(
      <ConversationList
        conversations={[]}
        selectedId={null}
        loading={false}
        error={null}
        search=""
        filter="all"
        onSearchChange={() => undefined}
        onFilterChange={() => undefined}
        onSelect={() => undefined}
        onRetry={() => undefined}
      />,
    );
    expect(screen.getByText("No conversations yet.")).toBeInTheDocument();
  });

  it("shows loading state", () => {
    render(
      <ConversationList
        conversations={[]}
        selectedId={null}
        loading
        error={null}
        search=""
        filter="all"
        onSearchChange={() => undefined}
        onFilterChange={() => undefined}
        onSelect={() => undefined}
        onRetry={() => undefined}
      />,
    );
    expect(screen.getByText("Loading conversations…")).toBeInTheDocument();
  });
});

describe("MessageBubble", () => {
  it("renders customer, AI, and human messages", () => {
    const messages: Message[] = [
      {
        id: "1",
        conversation_id: "c1",
        role: "user",
        direction: "inbound",
        channel: "sms",
        body: "Hello, can I get pricing?",
      },
      {
        id: "2",
        conversation_id: "c1",
        role: "assistant",
        direction: "outbound",
        channel: "sms",
        body: "Sure. Which service?",
        provider_status: "delivered",
      },
      {
        id: "3",
        conversation_id: "c1",
        role: "human",
        direction: "outbound",
        channel: "sms",
        body: "I can help with that.",
        provider_status: "sent",
      },
    ];

    const { rerender } = render(<MessageBubble message={messages[0]} />);
    expect(screen.getByText("Customer")).toBeInTheDocument();
    expect(screen.getByText("Hello, can I get pricing?")).toBeInTheDocument();

    rerender(<MessageBubble message={messages[1]} />);
    expect(screen.getByText("AI")).toBeInTheDocument();

    rerender(<MessageBubble message={messages[2]} />);
    expect(screen.getByText("You")).toBeInTheDocument();
  });

  it("shows AI is typing while streaming into one bubble", () => {
    render(
      <MessageBubble
        message={{
          id: "temp-stream",
          conversation_id: "c1",
          role: "assistant",
          direction: "outbound",
          channel: "whatsapp",
          body: "Sure —",
          streaming: true,
        }}
      />,
    );
    expect(screen.getByText("AI is typing…")).toBeInTheDocument();
    expect(screen.getByText(/Sure —/)).toBeInTheDocument();
  });
});

describe("MessageComposer", () => {
  it("disables send for empty messages and sends valid text", async () => {
    const onSend = vi.fn();
    render(
      <MessageComposer conversation={baseConversation} sending={false} onSend={onSend} />,
    );
    const sendButton = screen.getByRole("button", { name: "Send" });
    expect(sendButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText(/Type a message/i), {
      target: { value: "Hello there" },
    });
    expect(sendButton).not.toBeDisabled();
    fireEvent.click(sendButton);
    expect(onSend).toHaveBeenCalledWith("Hello there");
  });
});

describe("AIModeToggle and filters", () => {
  it("updates AI mode", () => {
    const onChange = vi.fn();
    render(<AIModeToggle aiEnabled onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Human" }));
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it("supports conversation filters", () => {
    const onChange = vi.fn();
    render(<ConversationFilters value="all" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Human Mode" }));
    expect(onChange).toHaveBeenCalledWith("human_mode");
  });
});
