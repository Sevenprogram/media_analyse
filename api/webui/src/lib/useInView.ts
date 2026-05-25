import React from "react";

export interface UseInViewOptions {
  once?: boolean;
  rootMargin?: string;
  threshold?: number;
}

export function useInView<T extends HTMLElement = HTMLDivElement>(options?: UseInViewOptions) {
  const once = options?.once ?? true;
  const rootMargin = options?.rootMargin ?? "160px 0px";
  const threshold = options?.threshold ?? 0.01;
  const [inView, setInView] = React.useState(false);
  const ref = React.useRef<T | null>(null);

  React.useEffect(() => {
    if (inView && once) return;
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setInView(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry) return;
        if (entry.isIntersecting) {
          setInView(true);
          if (once) observer.disconnect();
        } else if (!once) {
          setInView(false);
        }
      },
      { rootMargin, threshold },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [inView, once, rootMargin, threshold]);

  return { ref, inView };
}
