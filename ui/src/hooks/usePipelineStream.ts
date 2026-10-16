"use client";
import { useState, useCallback, useRef } from "react";
import type { PipelineState, SSEEvent, StageData } from "@/types/pipeline";
import { API_URL } from "@/lib/utils";
import { authHeaders } from "@/lib/optionsApi";

const INITIAL_STATE: PipelineState = {
  status:       "idle",
  currentStage: 0,
  stages:       {},
  fullResult:   null,
  error:        null,
  elapsed:      0,
  usage:        null,
};

export function usePipelineStream() {
  const [state, setState] = useState<PipelineState>(INITIAL_STATE);
  const abortRef  = useRef<AbortController | null>(null);
  const timerRef  = useRef<ReturnType<typeof setInterval> | null>(null);
  const startRef  = useRef<number>(0);

  const startPipeline = useCallback(async (ticker: string, exchange: string) => {
    // Cancel any in-flight request
    abortRef.current?.abort();
    if (timerRef.current) clearInterval(timerRef.current);

    abortRef.current = new AbortController();
    startRef.current = Date.now();

    setState({ ...INITIAL_STATE, status: "running" });

    // Elapsed timer
    timerRef.current = setInterval(() => {
      setState(prev => ({ ...prev, elapsed: (Date.now() - startRef.current) / 1000 }));
    }, 500);

    try {
      const res = await fetch(`${API_URL}/api/analyze`, {
        method:  "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body:    JSON.stringify({ ticker, exchange }),
        signal:  abortRef.current.signal,
      });

      if (!res.ok || !res.body) throw new Error(`API error ${res.status}`);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE lines
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const json = line.slice(6).trim();
          if (!json) continue;

          let event: SSEEvent;
          try { event = JSON.parse(json); } catch { continue; }

          // Error event
          if ("error" in event) {
            setState(prev => ({ ...prev, status: "error", error: event.error }));
            break;
          }

          // Done event
          if ("done" in event && event.done) {
            setState(prev => ({
              ...prev,
              status:     "done",
              currentStage: 6,
              fullResult: event.full_result,
              usage:      event.full_result.usage ?? prev.usage,
            }));
            break;
          }

          // Stage event
          if ("stage" in event) {
            setState(prev => {
              const stages: StageData = { ...prev.stages };

              if (event.status === "complete" && "payload" in event) {
                const p = event.payload as Record<string, unknown>;
                switch (event.stage) {
                  case 1: (stages as StageData).stage1 = p as StageData["stage1"]; break;
                  case 2: (stages as StageData).stage2 = p as StageData["stage2"]; break;
                  case 3: (stages as StageData).stage3 = p as StageData["stage3"]; break;
                  case 4: (stages as StageData).stage4 = p as StageData["stage4"]; break;
                  case 5: (stages as StageData).stage5 = p as StageData["stage5"]; break;
                  case 6: (stages as StageData).stage6 = p as StageData["stage6"]; break;
                }
              }

              return {
                ...prev,
                currentStage: event.stage,
                stages,
                usage: ("usage" in event && event.usage) ? event.usage : prev.usage,
              };
            });
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      setState(prev => ({
        ...prev,
        status: "error",
        error:  err instanceof Error ? err.message : String(err),
      }));
    } finally {
      if (timerRef.current) clearInterval(timerRef.current);
    }
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    if (timerRef.current) clearInterval(timerRef.current);
    setState(INITIAL_STATE);
  }, []);

  return { state, startPipeline, reset };
}
