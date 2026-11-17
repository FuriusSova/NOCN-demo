"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SubmitEvent } from "react";

type TimelineEvent = {
  stage: string;
  state: "complete" | "current" | "upcoming";
  date: string | null;
  description: string;
};

type Renewal = {
  id: string;
  reference: string;
  operator_name: string;
  card: {
    number: string;
    type: string;
    expiry_date: string;
    days_remaining: number;
    validity: string;
  };
  status: {
    label: string;
    explanation: string;
    updated_at: string;
  };
  next_action: {
    title: string;
    description: string;
    is_demo_assumption: boolean;
  };
  timeline: TimelineEvent[];
};

type Message = {
  id: string;
  text: string;
  sender: "operator" | "support";
  sender_name: string;
  created_at: string;
};

type PendingSubmission = { text: string; requestId: string };

const renewalId = "demo-renewal-1";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(new Date(value));
}

async function readError(response: Response) {
  const body: unknown = await response.json().catch(() => null);
  if (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    typeof body.error === "string"
  ) {
    return body.error;
  }
  return "Something went wrong. Please try again.";
}

export default function Home() {
  const [renewal, setRenewal] = useState<Renewal | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [messageText, setMessageText] = useState("");
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [sending, setSending] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pendingSubmission = useRef<PendingSubmission | null>(null);

  const loadPage = useCallback(async () => {
    try {
      const [renewalResponse, messagesResponse] = await Promise.all([
        fetch(`/api/renewals/${renewalId}`),
        fetch(`/api/renewals/${renewalId}/messages`),
      ]);
      if (!renewalResponse.ok) throw new Error(await readError(renewalResponse));
      if (!messagesResponse.ok) throw new Error(await readError(messagesResponse));
      const renewalData = (await renewalResponse.json()) as Renewal;
      const messagesData = (await messagesResponse.json()) as {
        messages: Message[];
      };
      setLoadError("");
      setRenewal(renewalData);
      setMessages(messagesData.messages);
    } catch (error) {
      setLoadError(
        error instanceof Error ? error.message : "Could not load this renewal.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadPage);
  }, [loadPage]);

  function focusMessageForm() {
    textareaRef.current?.focus();
  }

  async function submitMessage(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = messageText.trim();
    const characterCount = Array.from(trimmed).length;
    setFormError("");
    setNotice("");

    if (!trimmed) {
      setFormError("Enter a message before sending.");
      return;
    }
    if (characterCount > 2000) {
      setFormError("Messages must be 2,000 characters or fewer.");
      return;
    }

    if (!pendingSubmission.current || pendingSubmission.current.text !== trimmed) {
      pendingSubmission.current = {
        text: trimmed,
        requestId: crypto.randomUUID(),
      };
    }
    const submission = pendingSubmission.current;
    setSending(true);
    setNotice("Sending your message…");
    try {
      const response = await fetch(`/api/renewals/${renewalId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: submission.text,
          request_id: submission.requestId,
        }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const data = (await response.json()) as { message: Message };
      setMessages((current) =>
        [...current, data.message].sort((a, b) =>
          a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id),
        ),
      );
      setMessageText("");
      pendingSubmission.current = null;
      setNotice("Your message has been saved and linked to this renewal.");
    } catch (error) {
      setNotice("");
      setFormError(
        error instanceof Error
          ? `${error.message} Your message is still here; you can retry sending it.`
          : "Your message could not be sent. It is still here; please retry.",
      );
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return (
      <main className="page-shell">
        <p className="loading" role="status">Loading your renewal…</p>
      </main>
    );
  }

  if (loadError || !renewal) {
    return (
      <main className="page-shell">
        <p className="eyebrow">Renewals portal</p>
        <h1>My renewal</h1>
        <section className="panel error-panel" aria-labelledby="load-error">
          <h2 id="load-error">We could not load your renewal</h2>
          <p>{loadError || "Renewal details are unavailable."}</p>
          <button
            className="button button-primary"
            onClick={() => {
              setLoading(true);
              void loadPage();
            }}
          >
            Try again
          </button>
        </section>
      </main>
    );
  }

  const remainingLabel =
    renewal.card.days_remaining === 1
      ? "1 day remaining"
      : renewal.card.days_remaining >= 0
        ? `${renewal.card.days_remaining} days remaining`
        : `Expired ${Math.abs(renewal.card.days_remaining)} days ago`;

  return (
    <main className="page-shell">
      <header className="topbar">
        <div className="brand">Renewals portal</div>
        <span className="demo-label">Demo — fictional data</span>
      </header>

      <div className="intro" id="main-content">
        <div>
          <p className="eyebrow">Card-holder view</p>
          <h1>My renewal</h1>
          <p className="intro-copy">
            Hello, {renewal.operator_name}. Here is the latest on your card and renewal.
          </p>
        </div>
        <div className="reference">Renewal reference <strong>{renewal.reference}</strong></div>
      </div>

      <div className="content-grid">
        <div className="main-column">
          <section className="panel card-panel" aria-labelledby="card-heading">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Your card</p>
                <h2 id="card-heading">{renewal.operator_name}</h2>
              </div>
              <span className={`validity-badge ${renewal.card.validity === "Valid" ? "is-valid" : "is-expired"}`}>
                <span aria-hidden="true">{renewal.card.validity === "Valid" ? "✓" : "!"}</span>
                Card {renewal.card.validity.toLowerCase()}
              </span>
            </div>
            <dl className="card-details">
              <div>
                <dt>Card number</dt>
                <dd>{renewal.card.number}</dd>
              </div>
              <div>
                <dt>Card type</dt>
                <dd>{renewal.card.type}</dd>
              </div>
              <div>
                <dt>Expiry date</dt>
                <dd>{formatDate(renewal.card.expiry_date)}</dd>
              </div>
              <div>
                <dt>Time to expiry</dt>
                <dd>{remainingLabel}</dd>
              </div>
            </dl>
          </section>

          <section className="panel status-panel" aria-labelledby="status-heading">
            <div className="section-heading status-heading">
              <div>
                <p className="eyebrow">Renewal status</p>
                <h2 id="status-heading">{renewal.status.label}</h2>
              </div>
              <span className="status-icon" aria-hidden="true">!</span>
            </div>
            <p>{renewal.status.explanation}</p>
            <p className="status-update">
              <strong>Latest update:</strong> {formatTimestamp(renewal.status.updated_at)} —{" "}
              {renewal.status.explanation}
            </p>
            <p className="status-separation">
              Your renewal status is separate from your card validity. A message does not renew,
              approve or extend your card.
            </p>
          </section>

          <section className="panel action-panel" aria-labelledby="action-heading">
            <p className="eyebrow">What to do next</p>
            <h2 id="action-heading">{renewal.next_action.title}</h2>
            <span className="assumption-label">Demo assumption — not official CPCS policy</span>
            <p>{renewal.next_action.description}</p>
            <button className="button button-primary" onClick={focusMessageForm}>
              Ask about this renewal
            </button>
          </section>

          <section className="panel timeline-panel" aria-labelledby="timeline-heading">
            <p className="eyebrow">Renewal journey</p>
            <h2 id="timeline-heading">Progress</h2>
            <ol className="timeline">
              {renewal.timeline.map((item) => (
                <li className={`timeline-item ${item.state}`} key={item.stage}>
                  <span className="timeline-marker" aria-hidden="true">
                    {item.state === "complete" ? "✓" : item.state === "current" ? "●" : "○"}
                  </span>
                  <div className="timeline-copy">
                    <div className="timeline-title">
                      <h3>{item.stage}</h3>
                      <span className="stage-state">
                        {item.state === "complete"
                          ? "Completed"
                          : item.state === "current"
                            ? "In progress"
                            : "Upcoming"}
                      </span>
                    </div>
                    <p>{item.description}</p>
                    <time>
                      {item.date ? formatDate(item.date) : "Date not set"}
                    </time>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <aside className="panel conversation-panel" aria-labelledby="conversation-heading">
          <p className="eyebrow">Messages</p>
          <h2 id="conversation-heading">Renewal conversation</h2>
          <p className="muted conversation-intro">
            Messages are linked to renewal {renewal.reference}.
          </p>
          <div className="messages" aria-live="polite" aria-relevant="additions">
            {messages.length === 0 ? (
              <p className="empty-state">No messages yet. You can ask a question below.</p>
            ) : (
              messages.map((message) => (
                <article className={`message ${message.sender}`} key={message.id}>
                  <div className="message-meta">
                    <strong>{message.sender_name}</strong>
                    <span>{message.sender === "operator" ? "Operator" : "Support (demo)"}</span>
                  </div>
                  <p>{message.text}</p>
                  <time dateTime={message.created_at}>{formatTimestamp(message.created_at)}</time>
                </article>
              ))
            )}
          </div>
          <form className="message-form" onSubmit={submitMessage} noValidate>
            <label htmlFor="message">Your message</label>
            <p className="form-hint" id="message-hint">
              Up to 2,000 characters. Your message will be attached to this renewal automatically.
            </p>
            <textarea
              id="message"
              ref={textareaRef}
              value={messageText}
              onChange={(event) => {
                setMessageText(event.target.value);
                setFormError("");
              }}
              aria-describedby={`message-hint${formError ? " message-error" : ""}`}
              aria-invalid={Boolean(formError)}
              disabled={sending}
              rows={5}
            />
            <div className="character-count" aria-live="polite">
              {Array.from(messageText).length}/2,000 characters
            </div>
            {formError && <p className="inline-error" id="message-error" role="alert">{formError}</p>}
            <p className="sr-only" role="status" aria-live="polite">{notice}</p>
            <button className="button button-primary send-button" type="submit" disabled={sending}>
              {sending ? "Sending…" : "Send message"}
            </button>
          </form>
        </aside>
      </div>
    </main>
  );
}
