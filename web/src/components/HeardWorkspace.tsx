import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  api,
  clearToken,
  type Channel,
  type ChatThread,
  type CoachingMoment,
  type CurrentUser,
  type DMConversation,
  type DMMessage,
  type LeaderboardEntry,
  type LeaderboardResponse,
  type PriorityMoment,
  type SessionDetail,
  type SessionFeedback,
  type ThreadMessage,
  type TrainingSession,
  type TranscriptSegment,
} from "../api";
import { supabase } from "../supabase";
import {
  formatDate,
  formatDuration,
  formatPercent,
  formatRelativeDate,
  formatScore,
  formatTimestamp,
  initials,
  readableError,
} from "../utils";
import { AIMessageList, ChatComposer, DMMessageList } from "./Chat";
import { EmptyState, InlineError, LoadingRows } from "./States";

type Mode = "pre-training" | "post-training" | "leaderboard" | "dms";

const MODES: Array<{ id: Mode; label: string }> = [
  { id: "pre-training", label: "Pre-training" },
  { id: "post-training", label: "Post-training" },
  { id: "leaderboard", label: "Leaderboard" },
  { id: "dms", label: "DMs" },
];

type RouteState = {
  mode: Mode;
  channelId: string | null;
  itemId: string | null;
};

function parseRoute(pathname: string): RouteState {
  const parts = pathname.split("/").filter(Boolean).map((part) => {
    try {
      return decodeURIComponent(part);
    } catch {
      return part;
    }
  });
  const mode = MODES.some((item) => item.id === parts[0]) ? (parts[0] as Mode) : "pre-training";
  if (mode === "dms") return { mode, channelId: null, itemId: parts[1] ?? null };
  if (mode === "leaderboard") return { mode, channelId: parts[1] ?? null, itemId: null };
  return { mode, channelId: parts[1] ?? null, itemId: parts[2] ?? null };
}

function modeLabel(mode: Mode) {
  return MODES.find((item) => item.id === mode)?.label ?? "Pre-training";
}

function statusLabel(status: TrainingSession["status"]) {
  if (status === "ACTIVE") return "In progress";
  if (status === "PROCESSING") return "Processing";
  if (status === "FAILED") return "Analysis failed";
  return "Completed";
}

function findChannel(channels: Channel[], id: string | null) {
  if (!id) return null;
  return channels.find((channel) => channel.id === id || channel.slug === id) ?? null;
}

function WorkspaceHeader({
  eyebrow,
  title,
  meta,
  onBack,
  actions,
}: {
  eyebrow: string;
  title: string;
  meta?: string;
  onBack?: () => void;
  actions?: ReactNode;
}) {
  return (
    <header className="pane-header workspace-header">
      {onBack && (
        <button type="button" className="mobile-back" aria-label="Back to list" onClick={onBack}>‹</button>
      )}
      <div className="workspace-title">
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        {meta && <p className="header-meta">{meta}</p>}
      </div>
      {actions && <div className="header-actions">{actions}</div>}
    </header>
  );
}

function ContextHeader({ title, navOpen, setNavOpen }: { title: string; navOpen: boolean; setNavOpen: (open: boolean) => void }) {
  return (
    <header className="pane-header context-header">
      <div>
        <p className="eyebrow">Workspace</p>
        <h1>{title}</h1>
      </div>
      <button
        type="button"
        className="mobile-menu"
        aria-label="Open navigation"
        aria-expanded={navOpen}
        onClick={() => setNavOpen(true)}
      >
        Menu
      </button>
    </header>
  );
}

type ChannelContextProps = {
  mode: Exclude<Mode, "dms">;
  channels: Channel[];
  selectedChannel: Channel | null;
  loading: boolean;
  error: string;
  retry: () => void;
  navOpen: boolean;
  setNavOpen: (open: boolean) => void;
  children?: ReactNode;
};

function ChannelContext({
  mode,
  channels,
  selectedChannel,
  loading,
  error,
  retry,
  navOpen,
  setNavOpen,
  children,
}: ChannelContextProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return term
      ? channels.filter((channel) => `${channel.name} ${channel.description}`.toLowerCase().includes(term))
      : channels;
  }, [channels, query]);

  return (
    <section className="context-pane" id="context-pane" aria-label={`${modeLabel(mode)} navigation`}>
      <ContextHeader title={modeLabel(mode)} navOpen={navOpen} setNavOpen={setNavOpen} />
      <div className="context-search">
        <label htmlFor={`${mode}-channel-search`}>Search channels</label>
        <input
          id={`${mode}-channel-search`}
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search channels…"
        />
      </div>
      <div className="context-scroll">
        <div className="section-heading">
          <span>Channels</span>
          {!loading && !error && <span>{filtered.length}</span>}
        </div>
        {loading && <LoadingRows label="Loading channels" />}
        {error && <InlineError message={error} retry={retry} />}
        {!loading && !error && filtered.length === 0 && (
          <div className="inline-state"><p>{query ? "No channels match your search." : "No channels are available yet."}</p></div>
        )}
        {!loading && !error && (
          <div className="context-list channel-list">
            {filtered.map((channel) => {
              const active = selectedChannel?.id === channel.id;
              return (
                <button
                  key={channel.id}
                  type="button"
                  className={`context-row ${active ? "is-active" : ""}`}
                  aria-current={active ? "true" : undefined}
                  title={channel.description}
                  onClick={() => navigate(`/${mode}/${encodeURIComponent(channel.id)}`)}
                >
                  <span>
                    <strong>{channel.name}</strong>
                    <small>{channel.description}</small>
                  </span>
                  <span className="row-arrow" aria-hidden="true">›</span>
                </button>
              );
            })}
          </div>
        )}
        {selectedChannel && children}
      </div>
    </section>
  );
}

function PrimarySidebar({
  activeMode,
  currentUser,
  setNavOpen,
}: {
  activeMode: Mode;
  currentUser: CurrentUser | null;
  setNavOpen: (open: boolean) => void;
}) {
  const navigate = useNavigate();

  async function logout() {
    await api.logout().catch(() => undefined);
    await supabase.auth.signOut({ scope: "local" });
    clearToken();
    navigate("/login", { replace: true });
  }

  const displayName = currentUser?.profile.display_name ?? currentUser?.user.name ?? "Heard member";

  return (
    <>
      <button
        type="button"
        className="mobile-scrim"
        aria-label="Close navigation"
        onClick={() => setNavOpen(false)}
      />
      <aside className="primary-sidebar" aria-label="Primary navigation">
        <div className="brand-row">
          <span className="brand-mark" aria-hidden="true" />
          <span className="wordmark">HEARD</span>
          <button type="button" className="mobile-close" aria-label="Close navigation" onClick={() => setNavOpen(false)}>×</button>
        </div>
        <div className="sidebar-group">
          <p className="eyebrow">Workspace</p>
          <nav className="mode-list" aria-label="Heard workspace">
            {MODES.map((item) => {
              const active = item.id === activeMode;
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`mode-row ${active ? "is-active" : ""}`}
                  aria-current={active ? "page" : undefined}
                  aria-expanded={active}
                  aria-controls="context-pane"
                  onClick={() => navigate(`/${item.id}`)}
                >
                  <span className="chevron" aria-hidden="true">›</span>
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>
        <div className="sidebar-footer">
          <div className="user-summary">
            {currentUser?.profile.avatar_url ? (
              <img className="avatar" src={currentUser.profile.avatar_url} alt="" />
            ) : (
              <span className="avatar" aria-hidden="true">{initials(displayName)}</span>
            )}
            <span className="user-copy">
              <strong>{displayName}</strong>
              {currentUser?.profile.username && <small>@{currentUser.profile.username}</small>}
            </span>
          </div>
          <button type="button" className="text-action" onClick={() => void logout()}>Log out</button>
        </div>
      </aside>
    </>
  );
}

type SharedPaneProps = {
  channels: Channel[];
  selectedChannel: Channel | null;
  requestedChannelId: string | null;
  channelLoading: boolean;
  channelError: string;
  retryChannels: () => void;
  navOpen: boolean;
  setNavOpen: (open: boolean) => void;
};

function PreTrainingPanes({
  channels,
  selectedChannel,
  requestedChannelId,
  channelLoading,
  channelError,
  retryChannels,
  navOpen,
  setNavOpen,
  threadId,
}: SharedPaneProps & { threadId: string | null }) {
  const navigate = useNavigate();
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const [threadsError, setThreadsError] = useState("");
  const [activeThread, setActiveThread] = useState<ChatThread | null>(null);
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [threadLoading, setThreadLoading] = useState(false);
  const [threadError, setThreadError] = useState("");
  const [creating, setCreating] = useState(false);
  const [sending, setSending] = useState(false);
  const targetChannelId = selectedChannel?.id ?? requestedChannelId;
  const threadsRequest = useRef(0);
  const threadRequest = useRef(0);

  async function loadThreads() {
    if (!targetChannelId) return;
    const requestId = ++threadsRequest.current;
    setThreadsLoading(true);
    setThreadsError("");
    try {
      const response = await api.preTrainingThreads(targetChannelId);
      if (requestId === threadsRequest.current) setThreads(response.threads);
    } catch (error) {
      if (requestId === threadsRequest.current) setThreadsError(readableError(error, "Couldn’t load preparation chats."));
    } finally {
      if (requestId === threadsRequest.current) setThreadsLoading(false);
    }
  }

  useEffect(() => {
    setThreads([]);
    if (targetChannelId) void loadThreads();
  }, [targetChannelId]);

  async function loadThread() {
    const requestId = ++threadRequest.current;
    if (!threadId) {
      setActiveThread(null);
      setMessages([]);
      return;
    }
    setThreadLoading(true);
    setThreadError("");
    try {
      const response = await api.thread(threadId);
      if (requestId !== threadRequest.current) return;
      setActiveThread(response.thread);
      setMessages(response.messages);
    } catch (error) {
      if (requestId === threadRequest.current) setThreadError(readableError(error, "Couldn’t load this preparation chat."));
    } finally {
      if (requestId === threadRequest.current) setThreadLoading(false);
    }
  }

  useEffect(() => {
    void loadThread();
  }, [threadId]);

  async function createThread() {
    if (!selectedChannel || creating) return;
    setCreating(true);
    setThreadsError("");
    try {
      const response = await api.createPreTrainingThread(selectedChannel.id);
      setThreads((current) => [response.thread, ...current]);
      navigate(`/pre-training/${encodeURIComponent(selectedChannel.id)}/${encodeURIComponent(response.thread.id)}`);
    } catch (error) {
      setThreadsError(readableError(error, "Couldn’t start a preparation chat."));
    } finally {
      setCreating(false);
    }
  }

  async function sendMessage(content: string) {
    if (!activeThread) return;
    const optimistic: ThreadMessage = {
      id: `pending-${Date.now()}`,
      thread_id: activeThread.id,
      sender_type: "user",
      content,
      metadata: {},
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimistic]);
    setSending(true);
    setThreadError("");
    try {
      const response = await api.postThreadMessage(activeThread.id, content);
      setMessages((current) => [...current.filter((message) => message.id !== optimistic.id), response.message, response.reply]);
      void loadThreads();
    } catch (error) {
      setMessages((current) => current.filter((message) => message.id !== optimistic.id));
      setThreadError(readableError(error, "Heard couldn’t send that message."));
      throw error;
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <ChannelContext
        mode="pre-training"
        channels={channels}
        selectedChannel={selectedChannel}
        loading={channelLoading}
        error={channelError}
        retry={retryChannels}
        navOpen={navOpen}
        setNavOpen={setNavOpen}
      >
        <div className="context-divider" />
        <div className="section-heading"><span>Recent — {selectedChannel?.name}</span></div>
        {threadsLoading && <LoadingRows label="Loading preparation chats" />}
        {threadsError && <InlineError message={threadsError} retry={() => void loadThreads()} />}
        {!threadsLoading && !threadsError && threads.length === 0 && (
          <div className="inline-state"><p>No preparation chats yet.</p></div>
        )}
        {!threadsLoading && (
          <div className="context-list detail-list">
            {threads.map((thread) => (
              <button
                key={thread.id}
                type="button"
                className={`context-row compact ${thread.id === threadId ? "is-active" : ""}`}
                aria-current={thread.id === threadId ? "true" : undefined}
                onClick={() => navigate(`/pre-training/${encodeURIComponent(selectedChannel!.id)}/${encodeURIComponent(thread.id)}`)}
              >
                <span>
                  <strong>{thread.title || "Preparation chat"}</strong>
                  <small>{formatRelativeDate(thread.updated_at)}</small>
                </span>
                <span className="row-arrow" aria-hidden="true">›</span>
              </button>
            ))}
          </div>
        )}
        <div className="context-action">
          <button type="button" className="add-button" disabled={creating} onClick={() => void createThread()}>
            <span aria-hidden="true">＋</span>{creating ? "Starting…" : "New preparation"}
          </button>
        </div>
      </ChannelContext>

      <main className="workspace-pane" tabIndex={-1}>
        <WorkspaceHeader
          eyebrow={selectedChannel ? `${selectedChannel.name} · Pre-training` : "Pre-training"}
          title={activeThread?.title || selectedChannel?.name || "Preparation"}
          meta={selectedChannel ? "Prepare for your next speaking session" : undefined}
          onBack={threadId && selectedChannel ? () => navigate(`/pre-training/${encodeURIComponent(selectedChannel.id)}`) : undefined}
        />
        <div className="workspace-body conversation-body">
          {!selectedChannel && (
            <EmptyState title="Choose a channel" body="Select a channel from the middle pane to prepare with relevant speaking history." />
          )}
          {selectedChannel && !threadId && (
            <EmptyState
              title="Start a preparation chat"
              body="Talk through your audience, goal, structure, or the moment you want to handle with more confidence."
              action={<button className="secondary-button" type="button" disabled={creating} onClick={() => void createThread()}>New preparation</button>}
            />
          )}
          {threadLoading && <div className="workspace-loading"><LoadingRows label="Loading conversation" /></div>}
          {threadError && <InlineError message={threadError} retry={() => void loadThread()} />}
          {!threadLoading && !threadError && activeThread && <AIMessageList messages={messages} sending={sending} />}
        </div>
        {activeThread && (
          <ChatComposer
            label="Message Heard"
            placeholder="Ask Heard about your preparation…"
            busy={sending}
            onSend={sendMessage}
          />
        )}
      </main>
    </>
  );
}

function MetricStrip({ feedback }: { feedback: SessionFeedback }) {
  const metrics: Array<[string, number | null]> = [
    ["Overall", feedback.overall_score],
    ["Clarity", feedback.scores.clarity],
    ["Concise", feedback.scores.conciseness],
    ["Pace", feedback.scores.pace],
    ["Volume", feedback.scores.volume],
    ["Confidence", feedback.scores.confidence],
    ["Structure", feedback.scores.structure],
  ];
  return (
    <dl className="metrics-strip" aria-label="Session scores">
      {metrics.map(([label, value], index) => (
        <div key={label} className={index === 0 ? "is-overall" : ""}>
          <dt>{label}</dt>
          <dd>{formatScore(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function momentLabel(moment: CoachingMoment) {
  if (moment.timestamp_start != null && moment.timestamp_end != null) {
    return `${formatTimestamp(moment.timestamp_start)}–${formatTimestamp(moment.timestamp_end)}`;
  }
  return moment.segment_index != null ? `Segment ${moment.segment_index + 1}` : "Evidence";
}

function EvidenceList({
  title,
  moments,
  segments,
  onSelect,
}: {
  title: string;
  moments: Array<CoachingMoment | PriorityMoment>;
  segments: TranscriptSegment[];
  onSelect: (index: number) => void;
}) {
  if (!moments.length) return null;
  return (
    <section className="report-section">
      <div className="report-heading"><p className="eyebrow">{title}</p></div>
      <div className="evidence-list">
        {moments.map((moment, index) => {
          const matched = moment.segment_index != null && segments.some((segment) => segment.segment_index === moment.segment_index);
          return (
            <article className="evidence-row" key={`${title}-${moment.segment_index ?? "none"}-${index}`}>
              {matched ? (
                <button type="button" className="timestamp-button" onClick={() => onSelect(moment.segment_index!)}>
                  {momentLabel(moment)}
                </button>
              ) : (
                <span className="timestamp-label">{momentLabel(moment)}</span>
              )}
              <div>
                <strong>{"dimension" in moment && moment.dimension ? moment.dimension : moment.reason}</strong>
                {"recommendation" in moment && moment.recommendation && <p>{moment.recommendation}</p>}
                {moment.evidence && <blockquote>{moment.evidence}</blockquote>}
                {"dimension" in moment && moment.reason && <p className="secondary-copy">{moment.reason}</p>}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function PostTrainingReport({
  detail,
  segments,
  messages,
  selectedSegment,
  onSelectSegment,
  onMessagePeer,
  peerBusy,
  sending,
}: {
  detail: SessionDetail;
  segments: TranscriptSegment[];
  messages: ThreadMessage[];
  selectedSegment: number | null;
  onSelectSegment: (index: number) => void;
  onMessagePeer: (peer: LeaderboardEntry) => void;
  peerBusy: string;
  sending: boolean;
}) {
  const feedback = detail.feedback;
  if (!feedback) return null;

  const historical = feedback.longitudinal_analysis?.historical_summary;
  const improvement = historical?.improvement_from_baseline_percent ?? detail.progress.improvement_percent;
  const changes = [
    ...(feedback.longitudinal_analysis?.improvements_since_previous ?? []).map((change) => ({ change, direction: "up" as const })),
    ...(feedback.longitudinal_analysis?.regressions_since_previous ?? []).map((change) => ({ change, direction: "down" as const })),
  ];
  const hasSpeech = detail.session.total_words > 0;

  function selectSegment(index: number) {
    onSelectSegment(index);
    window.requestAnimationFrame(() => {
      const element = document.getElementById(`transcript-segment-${index}`);
      element?.scrollIntoView({ block: "center" });
      element?.focus({ preventScroll: true });
    });
  }

  return (
    <div className="report-content">
      {hasSpeech ? (
        <MetricStrip feedback={feedback} />
      ) : (
        <div className="no-speech-notice">No speech was captured, so this session’s scores are not presented as performance results.</div>
      )}

      <section className="report-section summary-section">
        <div className="report-heading"><p className="eyebrow">Session summary</p></div>
        <p className="report-summary">{feedback.summary || "No written summary is available for this session."}</p>
        <dl className="raw-metrics">
          <div><dt>Average pace</dt><dd>{feedback.average_wpm ? `${Math.round(feedback.average_wpm)} WPM` : "—"}</dd></div>
          <div><dt>Filler rate</dt><dd>{Number.isFinite(feedback.filler_rate) ? `${feedback.filler_rate.toFixed(1)} / 100 words` : "—"}</dd></div>
          <div><dt>Total fillers</dt><dd>{Number.isFinite(feedback.filler_count) ? feedback.filler_count : "—"}</dd></div>
        </dl>
      </section>

      {(improvement != null || changes.length > 0) && (
        <section className="report-section improvement-section">
          <div className="report-heading"><p className="eyebrow">Improvement</p></div>
          {improvement != null && (
            <div className="improvement-lead">
              <strong>{formatPercent(improvement)}</strong>
              <span>since baseline</span>
            </div>
          )}
          {changes.length > 0 && (
            <div className="change-list">
              {changes.map(({ change, direction }, index) => {
                return (
                  <article key={`${change.dimension}-${index}`}>
                    <span className={`trend-mark ${direction === "down" ? "is-down" : ""}`} aria-hidden="true">
                      {direction === "up" ? "↑" : "↓"}
                    </span>
                    <div>
                      <strong>{change.dimension}</strong>
                      {change.previous != null && change.current != null && (
                        <span className="change-values">{formatScore(change.previous)} → {formatScore(change.current)}</span>
                      )}
                      <p>{change.explanation}</p>
                      {change.evidence && <small>{change.evidence}</small>}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      )}

      {(feedback.stable_strengths.length > 0 || feedback.next_session_goals.length > 0) && (
        <section className="report-section split-feedback">
          {feedback.stable_strengths.length > 0 && (
            <div>
              <p className="eyebrow">Stable strengths</p>
              <ul className="plain-list">{feedback.stable_strengths.map((strength, index) => <li key={`${strength}-${index}`}>{strength}</li>)}</ul>
            </div>
          )}
          {feedback.next_session_goals.length > 0 && (
            <div>
              <p className="eyebrow">Next session</p>
              <ol className="goal-list">
                {feedback.next_session_goals.map((goal, index) => (
                  <li key={`${goal.goal}-${index}`}>
                    <strong>{goal.goal}</strong>
                    {goal.reason && <p>{goal.reason}</p>}
                    {goal.measurement && <small>{goal.measurement}</small>}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </section>
      )}

      <EvidenceList title="Strongest moments" moments={feedback.strongest_moments} segments={segments} onSelect={selectSegment} />
      <EvidenceList title="Priority moments" moments={feedback.priority_moments} segments={segments} onSelect={selectSegment} />

      {segments.length > 0 && (
        <section className="report-section transcript-section">
          <div className="report-heading">
            <p className="eyebrow">Transcript evidence</p>
            <span>{segments.length} segment{segments.length === 1 ? "" : "s"}</span>
          </div>
          <div className="transcript-list">
            {segments.map((segment) => (
              <article
                id={`transcript-segment-${segment.segment_index}`}
                key={segment.id}
                tabIndex={-1}
                className={segment.segment_index === selectedSegment ? "is-highlighted" : ""}
              >
                <header>
                  <span>{formatTimestamp(segment.start_seconds)}–{formatTimestamp(segment.end_seconds)}</span>
                  <span>{segment.word_count} words</span>
                </header>
                <p>{segment.transcript || "No transcript was captured for this segment."}</p>
              </article>
            ))}
          </div>
        </section>
      )}

      {detail.recommended_peers.length > 0 && (
        <section className="report-section peers-section">
          <div className="report-heading"><p className="eyebrow">People to learn from</p></div>
          <div className="peer-list">
            {detail.recommended_peers.map((peer) => (
              <article key={peer.user_id}>
                <span className="avatar" aria-hidden="true">{initials(peer.display_name ?? peer.username)}</span>
                <div>
                  <strong>{peer.display_name || peer.username || "Heard member"}</strong>
                  <small>#{peer.rank} · {formatPercent(peer.improvement_percent)} improvement</small>
                </div>
                <button type="button" className="small-button" disabled={peerBusy === peer.user_id} onClick={() => onMessagePeer(peer)}>
                  {peerBusy === peer.user_id ? "Opening…" : "Message"}
                </button>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="report-section coaching-section">
        <div className="report-heading">
          <div><p className="eyebrow">Heard coaching</p><h3>Ask about this session</h3></div>
        </div>
        {messages.length > 0 ? (
          <AIMessageList messages={messages} sending={sending} autoScroll={false} />
        ) : (
          <div className="inline-state"><p>No coaching messages yet. Ask a follow-up below.</p></div>
        )}
      </section>
    </div>
  );
}

function PostTrainingPanes({
  channels,
  selectedChannel,
  requestedChannelId,
  channelLoading,
  channelError,
  retryChannels,
  navOpen,
  setNavOpen,
  sessionId,
}: SharedPaneProps & { sessionId: string | null }) {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<TrainingSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsError, setSessionsError] = useState("");
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [creating, setCreating] = useState(false);
  const [sending, setSending] = useState(false);
  const [selectedSegment, setSelectedSegment] = useState<number | null>(null);
  const [peerBusy, setPeerBusy] = useState("");
  const targetChannelId = selectedChannel?.id ?? requestedChannelId;
  const sessionsRequest = useRef(0);
  const detailRequest = useRef(0);

  async function loadSessions() {
    if (!targetChannelId) return;
    const requestId = ++sessionsRequest.current;
    setSessionsLoading(true);
    setSessionsError("");
    try {
      const response = await api.channelSessions(targetChannelId);
      if (requestId === sessionsRequest.current) setSessions(response.sessions);
    } catch (error) {
      if (requestId === sessionsRequest.current) setSessionsError(readableError(error, "Couldn’t load training sessions."));
    } finally {
      if (requestId === sessionsRequest.current) setSessionsLoading(false);
    }
  }

  useEffect(() => {
    setSessions([]);
    if (targetChannelId) void loadSessions();
  }, [targetChannelId]);

  async function loadDetail() {
    const requestId = ++detailRequest.current;
    if (!sessionId) {
      setDetail(null);
      setSegments([]);
      setMessages([]);
      return;
    }
    setDetailLoading(true);
    setDetailError("");
    try {
      const [detailResponse, segmentResponse] = await Promise.all([api.session(sessionId), api.sessionSegments(sessionId)]);
      if (requestId !== detailRequest.current) return;
      setDetail(detailResponse);
      setSegments(segmentResponse.segments);
      if (detailResponse.thread) {
        const threadResponse = await api.thread(detailResponse.thread.id);
        if (requestId === detailRequest.current) setMessages(threadResponse.messages);
      } else {
        setMessages([]);
      }
    } catch (error) {
      if (requestId === detailRequest.current) setDetailError(readableError(error, "Couldn’t load this session."));
    } finally {
      if (requestId === detailRequest.current) setDetailLoading(false);
    }
  }

  useEffect(() => {
    setSelectedSegment(null);
    void loadDetail();
  }, [sessionId]);

  async function createSession() {
    if (!selectedChannel || creating) return;
    setCreating(true);
    setSessionsError("");
    try {
      const response = await api.createSession(selectedChannel.id);
      setSessions((current) => [response.session, ...current]);
      navigate(`/post-training/${encodeURIComponent(selectedChannel.id)}/${encodeURIComponent(response.session.id)}`);
    } catch (error) {
      setSessionsError(readableError(error, "Couldn’t start a training session."));
    } finally {
      setCreating(false);
    }
  }

  async function sendMessage(content: string) {
    if (!detail?.thread) return;
    const optimistic: ThreadMessage = {
      id: `pending-${Date.now()}`,
      thread_id: detail.thread.id,
      sender_type: "user",
      content,
      metadata: {},
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimistic]);
    setSending(true);
    setDetailError("");
    try {
      const response = await api.postThreadMessage(detail.thread.id, content);
      setMessages((current) => [...current.filter((message) => message.id !== optimistic.id), response.message, response.reply]);
    } catch (error) {
      setMessages((current) => current.filter((message) => message.id !== optimistic.id));
      setDetailError(readableError(error, "Heard couldn’t send that message."));
      throw error;
    } finally {
      setSending(false);
    }
  }

  async function messagePeer(peer: LeaderboardEntry) {
    setPeerBusy(peer.user_id);
    setDetailError("");
    try {
      const response = await api.openConversation(peer.user_id);
      navigate(`/dms/${encodeURIComponent(response.conversation_id)}`);
    } catch (error) {
      setDetailError(readableError(error, "Couldn’t open that conversation."));
    } finally {
      setPeerBusy("");
    }
  }

  const session = detail?.session ?? sessions.find((item) => item.id === sessionId) ?? null;
  const sessionMeta = session
    ? [formatDate(session.created_at), session.duration_seconds > 0 ? formatDuration(session.duration_seconds) : null, statusLabel(session.status)]
        .filter(Boolean)
        .join(" · ")
    : undefined;

  return (
    <>
      <ChannelContext
        mode="post-training"
        channels={channels}
        selectedChannel={selectedChannel}
        loading={channelLoading}
        error={channelError}
        retry={retryChannels}
        navOpen={navOpen}
        setNavOpen={setNavOpen}
      >
        <div className="context-divider" />
        <div className="section-heading"><span>Sessions — {selectedChannel?.name}</span></div>
        {sessionsLoading && <LoadingRows label="Loading sessions" />}
        {sessionsError && <InlineError message={sessionsError} retry={() => void loadSessions()} />}
        {!sessionsLoading && !sessionsError && sessions.length === 0 && (
          <div className="inline-state"><p>No training sessions yet.</p></div>
        )}
        {!sessionsLoading && (
          <div className="context-list detail-list">
            {sessions.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`context-row compact ${item.id === sessionId ? "is-active" : ""}`}
                aria-current={item.id === sessionId ? "true" : undefined}
                onClick={() => navigate(`/post-training/${encodeURIComponent(selectedChannel!.id)}/${encodeURIComponent(item.id)}`)}
              >
                <span>
                  <strong>{item.title || "Training session"}</strong>
                  <small>{formatRelativeDate(item.created_at)} · {item.status === "COMPLETED" ? formatDuration(item.duration_seconds) : statusLabel(item.status)}</small>
                </span>
                <span className="row-arrow" aria-hidden="true">›</span>
              </button>
            ))}
          </div>
        )}
        <div className="context-action">
          <button type="button" className="add-button" disabled={creating} onClick={() => void createSession()}>
            <span aria-hidden="true">＋</span>{creating ? "Starting…" : "Start training session"}
          </button>
        </div>
      </ChannelContext>

      <main className="workspace-pane post-workspace" tabIndex={-1}>
        <WorkspaceHeader
          eyebrow={selectedChannel ? `${selectedChannel.name} · Post-training` : "Post-training"}
          title={session?.title || selectedChannel?.name || "Session analysis"}
          meta={sessionMeta}
          onBack={sessionId && selectedChannel ? () => navigate(`/post-training/${encodeURIComponent(selectedChannel.id)}`) : undefined}
        />
        <div className="workspace-body post-body">
          {!selectedChannel && <EmptyState title="Choose a channel" body="Select a channel to review its completed speaking sessions and coaching history." />}
          {selectedChannel && !sessionId && (
            <EmptyState
              title={sessions.length ? "Choose a session" : "No completed sessions"}
              body={sessions.length ? "Select a session from the middle pane to review its analysis." : "Complete a speaking session and its analysis will appear here."}
              action={<button className="secondary-button" type="button" disabled={creating} onClick={() => void createSession()}>Start training session</button>}
            />
          )}
          {detailLoading && <div className="workspace-loading"><LoadingRows label="Loading session analysis" /></div>}
          {detailError && <InlineError message={detailError} retry={() => void loadDetail()} />}
          {!detailLoading && !detailError && detail && !detail.feedback && (
            <EmptyState
              title={detail.session.status === "FAILED" ? "Analysis unavailable" : detail.session.status === "COMPLETED" ? "No feedback available" : "Session in progress"}
              body={
                detail.session.status === "FAILED"
                  ? "Heard couldn’t complete this analysis. The session remains in your history."
                  : detail.session.status === "COMPLETED"
                    ? "This session completed without a feedback record."
                    : "Capture your speaking session with the existing training workflow. Feedback appears here after completion."
              }
            />
          )}
          {!detailLoading && !detailError && detail?.feedback && (
            <PostTrainingReport
              detail={detail}
              segments={segments}
              messages={messages}
              selectedSegment={selectedSegment}
              onSelectSegment={setSelectedSegment}
              onMessagePeer={(peer) => void messagePeer(peer)}
              peerBusy={peerBusy}
              sending={sending}
            />
          )}
        </div>
        {detail?.feedback && detail.thread && (
          <ChatComposer
            label="Ask Heard about this session"
            placeholder="Ask Heard about this session…"
            busy={sending}
            onSend={sendMessage}
          />
        )}
      </main>
    </>
  );
}

function LeaderboardPanes({
  channels,
  selectedChannel,
  requestedChannelId,
  channelLoading,
  channelError,
  retryChannels,
  navOpen,
  setNavOpen,
  currentUser,
}: SharedPaneProps & { currentUser: CurrentUser | null }) {
  const navigate = useNavigate();
  const [data, setData] = useState<LeaderboardResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [messageBusy, setMessageBusy] = useState("");
  const targetChannelId = selectedChannel?.id ?? requestedChannelId;
  const leaderboardRequest = useRef(0);

  async function loadLeaderboard() {
    const requestId = ++leaderboardRequest.current;
    if (!targetChannelId) {
      setData(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await api.leaderboard(targetChannelId);
      if (requestId === leaderboardRequest.current) setData(response);
    } catch (err) {
      if (requestId === leaderboardRequest.current) setError(readableError(err, "Couldn’t load this leaderboard."));
    } finally {
      if (requestId === leaderboardRequest.current) setLoading(false);
    }
  }

  useEffect(() => {
    void loadLeaderboard();
  }, [targetChannelId]);

  async function message(entry: LeaderboardEntry) {
    setMessageBusy(entry.user_id);
    setError("");
    try {
      const response = await api.openConversation(entry.user_id);
      navigate(`/dms/${encodeURIComponent(response.conversation_id)}`);
    } catch (err) {
      setError(readableError(err, "Couldn’t open that conversation."));
    } finally {
      setMessageBusy("");
    }
  }

  const currentUserId = currentUser?.user.id ?? data?.viewer_rank?.user_id ?? null;
  const viewerInPage = data?.entries.some((entry) => entry.user_id === currentUserId) ?? false;

  return (
    <>
      <ChannelContext
        mode="leaderboard"
        channels={channels}
        selectedChannel={selectedChannel}
        loading={channelLoading}
        error={channelError}
        retry={retryChannels}
        navOpen={navOpen}
        setNavOpen={setNavOpen}
      />
      <main className="workspace-pane" tabIndex={-1}>
        <WorkspaceHeader
          eyebrow="Leaderboard"
          title={selectedChannel?.name || "Channel standings"}
          meta={selectedChannel ? "Ranked by improvement across completed sessions" : undefined}
          onBack={selectedChannel ? () => navigate("/leaderboard") : undefined}
        />
        <div className="workspace-body leaderboard-body">
          {!selectedChannel && <EmptyState title="Choose a channel" body="Select a channel to compare improvement across completed sessions." />}
          {loading && <div className="workspace-loading"><LoadingRows label="Loading leaderboard" /></div>}
          {error && <InlineError message={error} retry={() => void loadLeaderboard()} />}
          {!loading && !error && data && data.entries.length === 0 && (
            <EmptyState title="No leaderboard yet" body="At least two completed sessions are required before improvement can be ranked." />
          )}
          {!loading && !error && data && data.entries.length > 0 && (
            <div className="leaderboard-wrap">
              <table className="leaderboard-table">
                <caption className="sr-only">{selectedChannel?.name} improvement leaderboard</caption>
                <thead><tr><th scope="col">#</th><th scope="col">Speaker</th><th scope="col">Improvement</th><th scope="col">Sessions</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>
                  {data.entries.map((entry) => {
                    const isMe = entry.user_id === currentUserId;
                    return (
                      <tr key={entry.user_id} className={isMe ? "is-current-user" : ""}>
                        <td className="rank-cell">{entry.rank}</td>
                        <td>
                          <span className="table-person">
                            <span className="avatar" aria-hidden="true">{initials(entry.display_name ?? entry.username)}</span>
                            <span><strong>{isMe ? `${entry.display_name || entry.username || "You"} (You)` : entry.display_name || entry.username || "Heard member"}</strong>{entry.username && <small>@{entry.username}</small>}</span>
                          </span>
                        </td>
                        <td className="improvement-cell">{formatPercent(entry.improvement_percent)}</td>
                        <td>{entry.completed_sessions}</td>
                        <td>{!isMe && <button type="button" className="small-button" disabled={messageBusy === entry.user_id} onClick={() => void message(entry)}>{messageBusy === entry.user_id ? "Opening…" : "Message"}</button>}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {!viewerInPage && data.viewer_rank && (
                <div className="viewer-rank">
                  <p className="eyebrow">Your rank</p>
                  <div><strong>{data.viewer_rank.rank}</strong><span>You</span><span>{formatPercent(data.viewer_rank.improvement_percent)}</span><span>{data.viewer_rank.completed_sessions} sessions</span></div>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </>
  );
}

function DMPanes({
  channels,
  channelLoading,
  navOpen,
  setNavOpen,
  conversationId,
  currentUser,
}: {
  channels: Channel[];
  channelLoading: boolean;
  navOpen: boolean;
  setNavOpen: (open: boolean) => void;
  conversationId: string | null;
  currentUser: CurrentUser | null;
}) {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<DMConversation[]>([]);
  const [messages, setMessages] = useState<DMMessage[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [error, setError] = useState("");
  const [messagesError, setMessagesError] = useState("");
  const [sending, setSending] = useState(false);
  const [discoveryChannel, setDiscoveryChannel] = useState("");
  const [peers, setPeers] = useState<LeaderboardEntry[]>([]);
  const [peersLoading, setPeersLoading] = useState(false);
  const [peerError, setPeerError] = useState("");
  const [peerBusy, setPeerBusy] = useState("");
  const messagesRequest = useRef(0);

  async function loadConversations() {
    setLoading(true);
    setError("");
    try {
      const response = await api.conversations();
      setConversations(response.conversations);
    } catch (err) {
      setError(readableError(err, "Couldn’t load your conversations."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadConversations();
  }, []);

  async function loadMessages() {
    const requestId = ++messagesRequest.current;
    if (!conversationId) {
      setMessages([]);
      return;
    }
    setMessagesLoading(true);
    setMessagesError("");
    try {
      const response = await api.dmMessages(conversationId);
      if (requestId !== messagesRequest.current) return;
      setMessages(response.messages);
      await api.markDMRead(conversationId).catch(() => undefined);
      setConversations((current) => current.map((conversation) => conversation.id === conversationId ? { ...conversation, unread_count: 0 } : conversation));
    } catch (err) {
      if (requestId === messagesRequest.current) setMessagesError(readableError(err, "Couldn’t load this conversation."));
    } finally {
      if (requestId === messagesRequest.current) setMessagesLoading(false);
    }
  }

  useEffect(() => {
    void loadMessages();
  }, [conversationId]);

  useEffect(() => {
    if (!discoveryChannel) {
      setPeers([]);
      setPeerError("");
      return;
    }
    let active = true;
    setPeersLoading(true);
    setPeerError("");
    api.recommendedPeers(discoveryChannel)
      .then((response) => { if (active) setPeers(response.peers); })
      .catch((err) => { if (active) setPeerError(readableError(err, "Couldn’t load recommended peers.")); })
      .finally(() => { if (active) setPeersLoading(false); });
    return () => { active = false; };
  }, [discoveryChannel]);

  async function sendMessage(content: string) {
    if (!conversationId) return;
    setSending(true);
    setMessagesError("");
    try {
      const response = await api.sendDM(conversationId, content);
      setMessages((current) => [...current, response.message]);
      void loadConversations();
    } catch (err) {
      setMessagesError(readableError(err, "Couldn’t send that message."));
      throw err;
    } finally {
      setSending(false);
    }
  }

  async function openPeer(peer: LeaderboardEntry) {
    setPeerBusy(peer.user_id);
    setPeerError("");
    try {
      const response = await api.openConversation(peer.user_id);
      navigate(`/dms/${encodeURIComponent(response.conversation_id)}`);
      void loadConversations();
    } catch (err) {
      setPeerError(readableError(err, "Couldn’t open that conversation."));
    } finally {
      setPeerBusy("");
    }
  }

  const selectedConversation = conversations.find((conversation) => conversation.id === conversationId) ?? null;
  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return conversations;
    return conversations.filter((conversation) => {
      const user = conversation.other_user;
      return `${user?.display_name ?? ""} ${user?.username ?? ""}`.toLowerCase().includes(term);
    });
  }, [conversations, query]);
  const otherUser = selectedConversation?.other_user;

  return (
    <>
      <section className="context-pane" id="context-pane" aria-label="Direct messages navigation">
        <ContextHeader title="DMs" navOpen={navOpen} setNavOpen={setNavOpen} />
        <div className="context-search">
          <label htmlFor="conversation-search">Search conversations</label>
          <input id="conversation-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search conversations…" />
        </div>
        <div className="context-scroll">
          <div className="section-heading"><span>Conversations</span>{!loading && <span>{filtered.length}</span>}</div>
          {loading && <LoadingRows label="Loading conversations" />}
          {error && <InlineError message={error} retry={() => void loadConversations()} />}
          {!loading && !error && filtered.length === 0 && <div className="inline-state"><p>{query ? "No conversations match your search." : "No conversations yet."}</p></div>}
          {!loading && !error && (
            <div className="context-list conversation-list">
              {filtered.map((conversation) => {
                const user = conversation.other_user;
                return (
                  <button
                    key={conversation.id}
                    type="button"
                    className={`context-row conversation-row ${conversation.id === conversationId ? "is-active" : ""}`}
                    aria-current={conversation.id === conversationId ? "true" : undefined}
                    onClick={() => navigate(`/dms/${encodeURIComponent(conversation.id)}`)}
                  >
                    <span className="avatar" aria-hidden="true">{initials(user?.display_name ?? user?.username)}</span>
                    <span className="conversation-copy">
                      <strong>{user?.display_name || user?.username || "Heard member"}</strong>
                      <small>{conversation.last_message?.content || "No messages yet"}</small>
                    </span>
                    <span className="conversation-meta">
                      <small>{formatRelativeDate(conversation.updated_at)}</small>
                      {conversation.unread_count > 0 && <span aria-label={`${conversation.unread_count} unread messages`}>{conversation.unread_count}</span>}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          <div className="context-divider" />
          <div className="peer-discovery">
            <div className="section-heading"><span>People by channel</span></div>
            <label htmlFor="peer-channel">Find improving speakers</label>
            <select id="peer-channel" value={discoveryChannel} disabled={channelLoading} onChange={(event) => setDiscoveryChannel(event.target.value)}>
              <option value="">Choose a channel</option>
              {channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
            </select>
            {peersLoading && <LoadingRows label="Loading recommended peers" />}
            {peerError && <InlineError message={peerError} />}
            {!peersLoading && discoveryChannel && !peerError && peers.length === 0 && <div className="inline-state"><p>No recommended peers are available yet.</p></div>}
            <div className="discovery-list">
              {peers.map((peer) => (
                <article key={peer.user_id}>
                  <span className="avatar" aria-hidden="true">{initials(peer.display_name ?? peer.username)}</span>
                  <span><strong>{peer.display_name || peer.username || "Heard member"}</strong><small>#{peer.rank} · {formatPercent(peer.improvement_percent)}</small></span>
                  <button type="button" className="small-button" disabled={peerBusy === peer.user_id} onClick={() => void openPeer(peer)}>{peerBusy === peer.user_id ? "…" : "Message"}</button>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      <main className="workspace-pane dm-workspace" tabIndex={-1}>
        <WorkspaceHeader
          eyebrow="Direct message"
          title={otherUser?.display_name || otherUser?.username || (conversationId ? "Conversation" : "Messages")}
          meta={otherUser?.username ? `@${otherUser.username}` : undefined}
          onBack={conversationId ? () => navigate("/dms") : undefined}
        />
        <div className="workspace-body dm-body">
          {!conversationId && <EmptyState title="Choose a conversation" body="Select a conversation from the middle pane, or find an improving speaker by channel." />}
          {messagesLoading && <div className="workspace-loading"><LoadingRows label="Loading messages" /></div>}
          {messagesError && <InlineError message={messagesError} retry={() => void loadMessages()} />}
          {!messagesLoading && !messagesError && conversationId && currentUser && <DMMessageList messages={messages} currentUserId={currentUser.user.id} />}
        </div>
        {conversationId && currentUser && (
          <ChatComposer label="Direct message" placeholder="Write a message…" busy={sending} onSend={sendMessage} />
        )}
      </main>
    </>
  );
}

export default function HeardWorkspace() {
  const location = useLocation();
  const route = parseRoute(location.pathname);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [navOpen, setNavOpen] = useState(false);
  const selectedChannel = findChannel(channels, route.channelId);

  async function loadShell() {
    setLoading(true);
    setError("");
    try {
      const [channelResponse, userResponse] = await Promise.all([api.channels(), api.me()]);
      setChannels(channelResponse.channels);
      setCurrentUser(userResponse);
    } catch (err) {
      setError(readableError(err, "Couldn’t load your Heard workspace."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadShell();
  }, []);

  useEffect(() => {
    setNavOpen(false);
    document.title = `${modeLabel(route.mode)} — Heard`;
  }, [location.pathname, route.mode]);

  const hasWorkspaceSelection =
    route.mode === "leaderboard" ? Boolean(route.channelId) :
      route.mode === "dms" ? Boolean(route.itemId) : Boolean(route.itemId);

  useEffect(() => {
    if (!hasWorkspaceSelection) return;
    window.requestAnimationFrame(() => {
      document.querySelector<HTMLElement>(".workspace-pane")?.focus({ preventScroll: true });
    });
  }, [location.pathname, hasWorkspaceSelection]);

  useEffect(() => {
    if (!navOpen) return;
    const sidebar = document.querySelector<HTMLElement>(".primary-sidebar");
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusable = Array.from(
      sidebar?.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])') ?? [],
    );
    window.requestAnimationFrame(() => focusable[0]?.focus());

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setNavOpen(false);
        return;
      }
      if (event.key !== "Tab" || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      previousFocus?.focus();
    };
  }, [navOpen]);

  const shared: SharedPaneProps = {
    channels,
    selectedChannel,
    requestedChannelId: route.channelId,
    channelLoading: loading,
    channelError: error,
    retryChannels: () => void loadShell(),
    navOpen,
    setNavOpen,
  };

  return (
    <div className={`app-shell ${hasWorkspaceSelection ? "has-selection" : ""} ${navOpen ? "nav-open" : ""}`}>
      <PrimarySidebar activeMode={route.mode} currentUser={currentUser} setNavOpen={setNavOpen} />
      <button
        type="button"
        className="workspace-nav-trigger"
        aria-label="Open navigation"
        aria-expanded={navOpen}
        onClick={() => setNavOpen(true)}
      >
        Menu
      </button>
      {route.mode === "pre-training" && <PreTrainingPanes {...shared} threadId={route.itemId} />}
      {route.mode === "post-training" && <PostTrainingPanes {...shared} sessionId={route.itemId} />}
      {route.mode === "leaderboard" && <LeaderboardPanes {...shared} currentUser={currentUser} />}
      {route.mode === "dms" && (
        <DMPanes
          channels={channels}
          channelLoading={loading}
          navOpen={navOpen}
          setNavOpen={setNavOpen}
          conversationId={route.itemId}
          currentUser={currentUser}
        />
      )}
    </div>
  );
}
