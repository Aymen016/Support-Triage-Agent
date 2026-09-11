import { useCallback, useRef, useState } from "react";
import { api } from "./api";

export interface RunProgress {
  isRunning: boolean;
  currentEmailSubject: string | null;
  lastStepLabel: string | null;
  totalDone: number;
}

/**
 * Wires the GET /run/stream SSE endpoint (see api/main.py) so the "Run agent
 * on new emails" button (Screen 1 top bar) can show live step-by-step
 * progress instead of a blank spinner. Falls back cleanly if EventSource
 * isn't available — the caller should offer api.run() as a non-streaming
 * alternative regardless.
 */
export function useAgentRun(onFinished: () => void) {
  const [progress, setProgress] = useState<RunProgress>({
    isRunning: false, currentEmailSubject: null, lastStepLabel: null, totalDone: 0,
  });
  const sourceRef = useRef<EventSource | null>(null);

  const start = useCallback(() => {
    if (sourceRef.current) return;
    setProgress({ isRunning: true, currentEmailSubject: null, lastStepLabel: null, totalDone: 0 });

    const source = new EventSource(api.runStreamUrl());
    sourceRef.current = source;

    source.addEventListener("email_start", (e) => {
      const data = JSON.parse((e as MessageEvent).data);
      setProgress((p) => ({ ...p, currentEmailSubject: data.subject, lastStepLabel: null }));
    });

    source.addEventListener("step", (e) => {
      const data = JSON.parse((e as MessageEvent).data);
      setProgress((p) => ({ ...p, lastStepLabel: data.tool_called }));
    });

    source.addEventListener("email_done", () => {
      setProgress((p) => ({ ...p, totalDone: p.totalDone + 1 }));
    });

    source.addEventListener("done", () => {
      source.close();
      sourceRef.current = null;
      setProgress((p) => ({ ...p, isRunning: false, currentEmailSubject: null, lastStepLabel: null }));
      onFinished();
    });

    source.onerror = () => {
      source.close();
      sourceRef.current = null;
      setProgress((p) => ({ ...p, isRunning: false }));
      onFinished();
    };
  }, [onFinished]);

  return { progress, start };
}
