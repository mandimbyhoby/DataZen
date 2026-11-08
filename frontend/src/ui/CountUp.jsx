/**
 * Fait défiler les chiffres clés (indicateurs, statistiques) de 0 à leur
 * valeur quand ils deviennent visibles.
 *
 * Le texte rendu par Django est conservé : seul le premier nœud texte de
 * chaque élément est animé, puis restauré à l'identique en fin d'animation
 * (séparateurs de milliers et décimales de la langue active compris).
 */
import { useEffect } from "react";
import { easeOutCubic, formatNumber, prefersReducedMotion } from "./motion.js";

const NUMBER = /^\s*(-?)(\d{1,3}(?:[\s  .,']\d{3})+|\d+)(?:([.,])(\d+))?\s*$/;

function parse(text) {
  const match = NUMBER.exec(text);
  if (!match) return null;
  const [, minus, integer, , fraction = ""] = match;
  const digits = integer.replace(/[^\d]/g, "");
  const value = Number(`${minus}${digits}${fraction ? `.${fraction}` : ""}`);
  return Number.isFinite(value) ? { value, decimals: fraction.length } : null;
}

function firstTextNode(element) {
  for (const node of element.childNodes) {
    if (node.nodeType === Node.TEXT_NODE && node.nodeValue.trim()) return node;
  }
  return null;
}

function animate(node, original, { value, decimals }) {
  const duration = 1000 + Math.min(600, Math.log10(Math.abs(value) + 1) * 150);
  const start = performance.now();
  const tick = (now) => {
    const progress = Math.min(1, (now - start) / duration);
    if (progress < 1) {
      node.nodeValue = formatNumber(value * easeOutCubic(progress), decimals);
      requestAnimationFrame(tick);
    } else {
      node.nodeValue = original;
    }
  };
  requestAnimationFrame(tick);
}

export default function CountUps({ elements }) {
  useEffect(() => {
    if (prefersReducedMotion() || !("IntersectionObserver" in window)) return undefined;
    const targets = new Map();
    elements.forEach((element) => {
      const node = firstTextNode(element);
      const parsed = node && parse(node.nodeValue);
      if (parsed && parsed.value !== 0) targets.set(element, { node, original: node.nodeValue, parsed });
    });
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const target = targets.get(entry.target);
          observer.unobserve(entry.target);
          if (target) animate(target.node, target.original, target.parsed);
        });
      },
      { rootMargin: "0px 0px -5% 0px" }
    );
    targets.forEach((_, element) => observer.observe(element));
    return () => observer.disconnect();
  }, [elements]);
  return null;
}
