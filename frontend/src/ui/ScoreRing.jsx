/**
 * Jauges circulaires animées pour les scores de qualité (sur 100).
 *
 * - <ScoreRing> : une jauge seule (score moyen du tableau de bord) ;
 * - <ScoreCompare> : deux jauges « avant → après » et l'écart en points
 *   (page d'un fichier).
 */
import { useId, useRef } from "react";
import { formatNumber, useAnimatedNumber, useInView } from "./motion.js";

const RADIUS = 52;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

// Les scores sont toujours affichés avec une décimale, comme côté serveur
// (« 85,0 / 100 »).
function decimalsOf() {
  return 1;
}

export function ScoreRing({ value, label, size = 132, tone = "brand", delay = 0 }) {
  const ref = useRef(null);
  const inView = useInView(ref);
  const gradientId = useId().replace(/:/g, "");
  const current = useAnimatedNumber(value ?? 0, { active: inView && value != null, duration: 1200 + delay });
  const ratio = value == null ? 0 : Math.max(0, Math.min(100, current)) / 100;

  return (
    <figure ref={ref} className={`dz-ring dz-ring--${tone}`} style={{ "--dz-ring-size": `${size}px` }}>
      <svg viewBox="0 0 128 128" role="img" aria-label={`${label} : ${value == null ? "—" : formatNumber(value, decimalsOf(value))} / 100`}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" className="dz-ring__stop-a" />
            <stop offset="100%" className="dz-ring__stop-b" />
          </linearGradient>
        </defs>
        <circle className="dz-ring__track" cx="64" cy="64" r={RADIUS} />
        <circle
          className="dz-ring__value"
          cx="64"
          cy="64"
          r={RADIUS}
          stroke={`url(#${gradientId})`}
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={CIRCUMFERENCE * (1 - ratio)}
        />
      </svg>
      <div className="dz-ring__center" aria-hidden="true">
        <span className="dz-ring__number">
          {value == null ? "—" : formatNumber(current, decimalsOf(value))}
        </span>
        <span className="dz-ring__unit">/100</span>
      </div>
      {label ? <figcaption className="dz-ring__label">{label}</figcaption> : null}
    </figure>
  );
}

export function ScoreCompare({ before, after, labelBefore, labelAfter }) {
  const delta = before != null && after != null ? Math.round((after - before) * 10) / 10 : null;
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : "±";
  return (
    <div className="dz-score-compare">
      <ScoreRing value={before} label={labelBefore} tone="muted" size={116} />
      <div className="dz-score-compare__arrow" aria-hidden="true">
        <svg viewBox="0 0 48 24" width="48" height="24">
          <path d="M2 12h40m-8-8 8 8-8 8" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {delta != null ? (
          <span className={`dz-delta ${delta > 0 ? "is-up" : delta < 0 ? "is-down" : ""}`}>
            {sign}
            {formatNumber(Math.abs(delta), decimalsOf(delta))}
          </span>
        ) : null}
      </div>
      <ScoreRing value={after} label={labelAfter} tone={after == null ? "muted" : "brand"} size={132} delay={200} />
    </div>
  );
}
