/**
 * Notifications « toast » : les messages Django (`.alert`) glissent en haut à
 * droite. Les confirmations disparaissent seules ; les erreurs et
 * avertissements restent jusqu'à ce que l'utilisateur les ferme.
 */
import { useCallback, useEffect, useState } from "react";

const AUTO_CLOSE_MS = 6000;
const PERSISTENT = new Set(["danger", "warning", "error"]);
const ICONS = { success: "✓", danger: "!", error: "!", warning: "!", info: "i" };

function Toast({ toast, closeLabel, onClose }) {
  const [leaving, setLeaving] = useState(false);
  const persistent = PERSISTENT.has(toast.level);

  const close = useCallback(() => {
    setLeaving(true);
    window.setTimeout(() => onClose(toast.id), 220);
  }, [onClose, toast.id]);

  useEffect(() => {
    if (persistent) return undefined;
    const timer = window.setTimeout(close, AUTO_CLOSE_MS);
    return () => window.clearTimeout(timer);
  }, [close, persistent]);

  return (
    <div
      className={`dz-toast dz-toast--${toast.level} ${leaving ? "is-leaving" : ""}`}
      role={persistent ? "alert" : "status"}
    >
      <span className="dz-toast__icon" aria-hidden="true">{ICONS[toast.level] || "i"}</span>
      <div className="dz-toast__body">{toast.text}</div>
      <button type="button" className="dz-toast__close" aria-label={closeLabel} onClick={close}>
        ×
      </button>
      {persistent ? null : (
        <span className="dz-toast__timer" style={{ animationDuration: `${AUTO_CLOSE_MS}ms` }} aria-hidden="true" />
      )}
    </div>
  );
}

export default function Toaster({ initial, closeLabel }) {
  const [toasts, setToasts] = useState(initial);
  const remove = useCallback((id) => setToasts((list) => list.filter((t) => t.id !== id)), []);
  return (
    <div className="dz-toaster" aria-live="polite">
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} closeLabel={closeLabel} onClose={remove} />
      ))}
    </div>
  );
}
