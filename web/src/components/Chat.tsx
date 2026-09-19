import { useEffect, useRef, useState } from "react";
import type { DMMessage, ThreadMessage } from "../api";
import { formatDate } from "../utils";
import RichText from "./RichText";

type ComposerProps = {
  label: string;
  placeholder: string;
  onSend: (value: string) => Promise<void>;
  busy?: boolean;
  disabled?: boolean;
};

export function ChatComposer({ label, placeholder, onSend, busy = false, disabled = false }: ComposerProps) {
  const [value, setValue] = useState("");

  async function submit() {
    const content = value.trim();
    if (!content || busy || disabled) return;
    try {
      await onSend(content);
      setValue("");
    } catch {
      // The parent owns the visible error state; keep the draft for retry.
    }
  }

  return (
    <div className="composer-wrap">
      <div className="composer">
        <label className="sr-only" htmlFor="active-composer">{label}</label>
        <textarea
          id="active-composer"
          rows={1}
          value={value}
          placeholder={placeholder}
          disabled={disabled}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              void submit();
            }
          }}
        />
        <button
          type="button"
          className="send-button"
          aria-label="Send message"
          disabled={disabled || busy || !value.trim()}
          onClick={() => void submit()}
        >
          <span aria-hidden="true">↑</span>
        </button>
      </div>
      <span className="composer-hint">Enter to send · Shift + Enter for a new line</span>
    </div>
  );
}

export function AIMessageList({
  messages,
  sending = false,
  autoScroll = true,
}: {
  messages: ThreadMessage[];
  sending?: boolean;
  autoScroll?: boolean;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const visibleMessages = messages.filter((message) => message.sender_type !== "transcript");

  useEffect(() => {
    if (autoScroll) endRef.current?.scrollIntoView({ block: "end" });
  }, [visibleMessages.length, sending, autoScroll]);

  if (visibleMessages.length === 0 && !sending) {
    return (
      <div className="conversation-empty">
        <span className="empty-rule" aria-hidden="true" />
        <h3>No messages yet</h3>
        <p>Start the conversation when you’re ready.</p>
      </div>
    );
  }

  return (
    <div className="message-stream" aria-live="polite">
      {visibleMessages.map((message) => {
        if (message.sender_type === "system") {
          return <p className="system-message" key={message.id}>{message.content}</p>;
        }
        const assistant = message.sender_type === "assistant";
        return (
          <article className={`ai-message ${assistant ? "is-assistant" : "is-user"}`} key={message.id}>
            <header>
              <strong>{assistant ? "Heard" : "You"}</strong>
              <time dateTime={message.created_at}>{formatDate(message.created_at, true)}</time>
            </header>
            <RichText content={message.content} />
          </article>
        );
      })}
      {sending && (
        <div className="thinking-row" role="status">
          <span /><span /><span />
          <span className="sr-only">Heard is responding</span>
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}

export function DMMessageList({ messages, currentUserId }: { messages: DMMessage[]; currentUserId: string }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  if (messages.length === 0) {
    return (
      <div className="conversation-empty">
        <span className="empty-rule" aria-hidden="true" />
        <h3>No messages yet</h3>
        <p>Start the conversation.</p>
      </div>
    );
  }

  return (
    <div className="dm-stream" aria-live="polite">
      {messages.map((message) => {
        const mine = message.sender_id === currentUserId;
        return (
          <article className={`dm-message ${mine ? "is-mine" : "is-theirs"}`} key={message.id}>
            <p>{message.content}</p>
            <time dateTime={message.created_at}>{formatDate(message.created_at, true)}</time>
          </article>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
