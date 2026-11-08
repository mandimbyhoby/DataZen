/**
 * Petits utilitaires d'animation partagés par les îlots React de l'interface.
 *
 * Toutes les animations respectent « réduire les animations » : la valeur
 * finale est alors affichée immédiatement.
 */
import { useEffect, useRef, useState } from "react";

export function prefersReducedMotion() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** Courbe d'accélération douce (ease-out cubique). */
export function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

/**
 * Anime un nombre de 0 jusqu'à `target` dès que `active` devient vrai.
 * Renvoie la valeur courante.
 */
export function useAnimatedNumber(target, { active = true, duration = 1100 } = {}) {
  const [value, setValue] = useState(prefersReducedMotion() ? target : 0);
  const frame = useRef(0);

  useEffect(() => {
    if (!active) return undefined;
    if (prefersReducedMotion() || !Number.isFinite(target)) {
      setValue(target);
      return undefined;
    }
    const start = performance.now();
    const tick = (now) => {
      const progress = Math.min(1, (now - start) / duration);
      setValue(target * easeOutCubic(progress));
      if (progress < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [target, active, duration]);

  return value;
}

/** Vrai dès que l'élément référencé entre dans la fenêtre (une seule fois). */
export function useInView(ref, { rootMargin = "0px 0px -10% 0px" } = {}) {
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node || inView) return undefined;
    if (!("IntersectionObserver" in window)) {
      setInView(true);
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setInView(true);
          observer.disconnect();
        }
      },
      { rootMargin }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref, inView, rootMargin]);
  return inView;
}

/** Langue de la page (attribut `lang` posé par Django). */
export function pageLocale() {
  return document.documentElement.lang || "fr";
}

/** Formate un nombre selon la langue de la page. */
export function formatNumber(value, decimals = 0) {
  try {
    return new Intl.NumberFormat(pageLocale(), {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(value);
  } catch (error) {
    return value.toFixed(decimals);
  }
}
