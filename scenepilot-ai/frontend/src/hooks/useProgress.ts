/**
 * useProgress — subscribes to the SSE progress stream for a given story_id.
 *
 * Returns the latest progress event data, or null when idle.
 * The EventSource is opened when `storyId` is set and closed automatically
 * when the `done` event fires or when `storyId` is cleared.
 */
import { useState, useEffect, useRef } from "react";

export interface ProgressEvent {
  stage: string;
  message: string;
  retry?: number;
  approved?: boolean;
}

export function useProgress(storyId: string | null): ProgressEvent | null {
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    // Close any previous connection
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setProgress(null);

    if (!storyId) return;

    const es = new EventSource(`/api/progress/${storyId}`);
    esRef.current = es;

    es.addEventListener("progress", (e: MessageEvent) => {
      try {
        setProgress(JSON.parse(e.data) as ProgressEvent);
      } catch {
        /* ignore malformed events */
      }
    });

    es.addEventListener("done", () => {
      es.close();
      esRef.current = null;
      // Keep the last progress message visible briefly then clear
      setTimeout(() => setProgress(null), 800);
    });

    es.addEventListener("error", () => {
      es.close();
      esRef.current = null;
    });

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [storyId]);

  return progress;
}
