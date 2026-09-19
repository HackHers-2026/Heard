export function LoadingRows({ label = "Loading" }: { label?: string }) {
  return (
    <div className="skeleton-list" role="status" aria-label={label}>
      <span /><span /><span />
    </div>
  );
}

export function InlineError({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="inline-state is-error" role="alert">
      <p>{message}</p>
      {retry && <button type="button" className="text-action" onClick={retry}>Retry</button>}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return (
    <div className="workspace-empty">
      <span className="empty-rule" aria-hidden="true" />
      <h3>{title}</h3>
      <p>{body}</p>
      {action && <div className="empty-action">{action}</div>}
    </div>
  );
}
