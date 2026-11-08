/**
 * Zone de téléversement interactive (page d'accueil).
 *
 * Remplace visuellement la zone de dépôt rendue par Django, mais réutilise
 * son formulaire : jeton CSRF, champ `file` et URL d'envoi restent ceux du
 * serveur. Le fichier choisi est recopié dans le vrai champ, si bien qu'en
 * cas d'erreur serveur un envoi classique du formulaire prend le relais.
 *
 * Étapes : vide → fichier choisi → envoi (progression réelle) → succès.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { pageLocale } from "./motion.js";

const DETAIL_URL = /\/datasets\/\d+\/?$/;

function extensionOf(name) {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

function formatSize(bytes) {
  const megabytes = bytes / (1024 * 1024);
  const [value, unit] = megabytes >= 1 ? [megabytes, "megabyte"] : [bytes / 1024, "kilobyte"];
  try {
    return new Intl.NumberFormat(pageLocale(), {
      style: "unit",
      unit,
      unitDisplay: "short",
      maximumFractionDigits: value < 10 ? 1 : 0,
    }).format(value);
  } catch (error) {
    return `${value.toFixed(1)} ${unit === "megabyte" ? "MB" : "KB"}`;
  }
}

function FileBadge({ ext }) {
  const label = ext.replace(".", "").toUpperCase() || "?";
  const tone = ext === ".csv" ? "csv" : "xls";
  return (
    <span className={`dz-upload__badge dz-upload__badge--${tone}`} aria-hidden="true">
      <svg viewBox="0 0 40 48" width="40" height="48">
        <path d="M4 4a4 4 0 0 1 4-4h18l10 10v34a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z" className="dz-upload__sheet" />
        <path d="M26 0v6a4 4 0 0 0 4 4h6" className="dz-upload__fold" />
      </svg>
      <span>{label}</span>
    </span>
  );
}

function CloudIcon() {
  return (
    <svg viewBox="0 0 64 64" width="56" height="56" aria-hidden="true" className="dz-upload__cloud">
      <path d="M20 46h-3a11 11 0 0 1-1.6-21.9A16 16 0 0 1 46.3 20 12 12 0 0 1 47 46h-3" />
      <path d="M32 52V30m-9 9 9-9 9 9" />
    </svg>
  );
}

export default function UploadZone({ form, input, messages, maxSize, accept }) {
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [phase, setPhase] = useState("idle"); // idle | ready | uploading | done | failed
  const [progress, setProgress] = useState(0);
  const picker = useRef(null);
  const dragDepth = useRef(0);

  const choose = useCallback(
    (candidate) => {
      if (!candidate) return;
      if (!accept.includes(extensionOf(candidate.name))) {
        setError(messages.format);
        return;
      }
      if (candidate.size > maxSize) {
        setError(messages.size);
        return;
      }
      // Recopie dans le vrai champ du formulaire (repli : envoi classique).
      try {
        const transfer = new DataTransfer();
        transfer.items.add(candidate);
        input.files = transfer.files;
      } catch (copyError) {
        /* Navigateur ancien : seul l'envoi XHR transportera le fichier. */
      }
      setError("");
      setFile(candidate);
      setPhase("ready");
      setProgress(0);
    },
    [accept, input, maxSize, messages]
  );

  const reset = () => {
    setFile(null);
    setPhase("idle");
    setError("");
    setProgress(0);
    try {
      input.value = "";
    } catch (resetError) {
      /* ignoré */
    }
    if (picker.current) picker.current.value = "";
  };

  const upload = useCallback(() => {
    if (!file) return;
    const data = new FormData(form);
    data.set(input.name, file, file.name);

    const request = new XMLHttpRequest();
    request.open("POST", form.getAttribute("action") || window.location.href);
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) setProgress(Math.round((event.loaded / event.total) * 100));
    });
    request.addEventListener("load", () => {
      const target = request.responseURL ? new URL(request.responseURL) : null;
      if (request.status < 400 && target && DETAIL_URL.test(target.pathname)) {
        setProgress(100);
        setPhase("done");
        window.setTimeout(() => window.location.assign(target.href), 650);
      } else {
        // Le serveur a refusé le fichier : l'envoi classique affiche ses
        // messages d'erreur à l'endroit habituel.
        form.submit();
      }
    });
    request.addEventListener("error", () => setPhase("failed"));
    setPhase("uploading");
    setProgress(0);
    request.send(data);
  }, [file, form, input]);

  // Le bouton « Analyser et nettoyer » d'origine reste la seule action
  // d'envoi : on intercepte la soumission du formulaire.
  useEffect(() => {
    const onSubmit = (event) => {
      if (!file) {
        event.preventDefault();
        setError(messages.empty);
        picker.current?.click();
        return;
      }
      event.preventDefault();
      if (phase === "ready" || phase === "failed") upload();
    };
    form.addEventListener("submit", onSubmit);
    return () => form.removeEventListener("submit", onSubmit);
  }, [file, form, messages.empty, phase, upload]);

  const onDragEnter = (event) => {
    event.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  };
  const onDragLeave = (event) => {
    event.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  };
  const onDrop = (event) => {
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    if (phase === "uploading" || phase === "done") return;
    choose(event.dataTransfer.files && event.dataTransfer.files[0]);
  };

  const busy = phase === "uploading" || phase === "done";

  return (
    <div
      className={`dz-upload is-${phase} ${dragging ? "is-dragging" : ""} ${error ? "has-error" : ""}`}
      onDragEnter={onDragEnter}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <input
        ref={picker}
        type="file"
        accept={accept.join(",")}
        className="dz-upload__picker"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => choose(event.target.files && event.target.files[0])}
      />

      {file ? (
        <div className="dz-upload__file">
          <FileBadge ext={extensionOf(file.name)} />
          <div className="dz-upload__meta">
            <div className="dz-upload__name" title={file.name}>{file.name}</div>
            <div className="dz-upload__size">
              {formatSize(file.size)}
              {phase === "uploading" ? ` · ${messages.uploading} ${progress} %` : null}
              {phase === "done" ? ` · ${messages.done}` : null}
            </div>
            <div className="dz-upload__bar" aria-hidden={phase === "ready"}>
              <span style={{ width: `${phase === "ready" ? 0 : progress}%` }} />
            </div>
          </div>
          {busy ? (
            <span className={`dz-upload__state ${phase === "done" ? "is-done" : ""}`} aria-hidden="true">
              {phase === "done" ? "✓" : ""}
            </span>
          ) : (
            <button type="button" className="dz-upload__remove" onClick={reset} aria-label={messages.remove} title={messages.remove}>
              ×
            </button>
          )}
        </div>
      ) : (
        <button type="button" className="dz-upload__target" onClick={() => picker.current?.click()}>
          <CloudIcon />
          <span className="dz-upload__title">{dragging ? messages.release : messages.drop}</span>
          <span className="dz-upload__hint">{messages.browse}</span>
          <span className="dz-upload__formats">
            {accept.map((ext) => (
              <code key={ext}>{ext}</code>
            ))}
            <span>· {formatSize(maxSize)}</span>
          </span>
        </button>
      )}

      <div className="dz-upload__feedback" role="status" aria-live="polite">
        {error ? <span className="dz-upload__error">{error}</span> : null}
        {phase === "failed" ? <span className="dz-upload__error">{messages.failed}</span> : null}
      </div>
    </div>
  );
}
