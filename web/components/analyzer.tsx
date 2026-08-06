"use client";

import { useRef, useState, type FormEvent } from "react";
import { languageName } from "@/lib/format";
import type { AnalyzeResult } from "@/lib/types";
import { AlertIcon } from "./icons";
import { LanguageBadge, ToxicityBadge } from "./toxicity-badge";

const SAMPLES = [
  "You are an amazing person, thank you for this",
  "eres un idiota de mierda, callate ya",
  "ты тупой урод, заткнись уже",
  "この記事はとても勉強になりました",
  "seni aptal şerefsiz, defol git",
  "sh1t take, you're an 1diot",
];

/**
 * Paste-anything playground. One post per line so several languages can be
 * compared side by side — the fastest way to see the model behave.
 */
export function Analyzer() {
  const [value, setValue] = useState("");
  const [results, setResults] = useState<AnalyzeResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  async function analyze(texts: string[]) {
    setPending(true);
    setError(null);
    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texts }),
      });
      const body = await response.json();
      if (!response.ok) {
        setError(body?.error ?? `Request failed (HTTP ${response.status})`);
        setResults(null);
        return;
      }
      setResults(body.results as AnalyzeResult[]);
    } catch {
      setError("Network error. Is the analysis service running?");
      setResults(null);
    } finally {
      setPending(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const texts = value
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (texts.length === 0) {
      setError("Type something to analyze first.");
      textareaRef.current?.focus();
      return;
    }
    void analyze(texts.slice(0, 50));
  }

  function loadSamples() {
    const text = SAMPLES.join("\n");
    setValue(text);
    void analyze(SAMPLES);
  }

  return (
    <div className="px-4 py-5">
      <form onSubmit={onSubmit} noValidate>
        <label htmlFor="analyze-input" className="mb-1.5 block text-[13px] font-medium text-muted">
          Text to score — one post per line, any language
        </label>
        <textarea
          id="analyze-input"
          ref={textareaRef}
          value={value}
          rows={5}
          onChange={(event) => {
            setValue(event.target.value);
            if (error) setError(null);
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "analyze-error" : undefined}
          placeholder={"Write or paste text here…\nOne line per post"}
          className="w-full resize-y rounded-2xl border border-line bg-raised p-3 text-[15px] leading-6 outline-none transition-colors duration-200 focus:border-brand placeholder:text-muted"
        />
        {error && (
          <p id="analyze-error" role="alert" className="mt-1.5 flex items-center gap-1.5 text-[13px] text-toxic">
            <AlertIcon className="h-4 w-4" />
            {error}
          </p>
        )}

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="submit"
            disabled={pending}
            className="flex h-11 cursor-pointer items-center gap-2 rounded-full bg-brand px-5 text-[15px] font-bold text-white transition-colors duration-200 hover:bg-brand-hover disabled:cursor-progress disabled:opacity-60"
          >
            {pending && (
              <span
                aria-hidden="true"
                className="spin h-4 w-4 rounded-full border-2 border-white/40 border-t-white"
              />
            )}
            {pending ? "Scoring…" : "Score text"}
          </button>
          <button
            type="button"
            onClick={loadSamples}
            disabled={pending}
            className="flex h-11 cursor-pointer items-center rounded-full border border-line px-5 text-[15px] font-bold transition-colors duration-200 hover:bg-hover disabled:opacity-60"
          >
            Load multilingual samples
          </button>
        </div>
      </form>

      <div aria-live="polite" className="mt-6">
        {results && results.length > 0 && (
          <>
            <h2 className="mb-3 text-[15px] font-bold">
              {results.length} {results.length === 1 ? "result" : "results"}
            </h2>
            <ul className="flex flex-col gap-2">
              {results.map((result, index) => (
                <li
                  key={index}
                  className="fade-rise rounded-2xl border border-line p-3"
                  style={{ animationDelay: `${Math.min(index, 12) * 30}ms` }}
                >
                  <p className="text-[15px] leading-6 break-words">{result.text}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <ToxicityBadge toxicity={result} />
                    <LanguageBadge code={result.language} />
                    <span className="text-[12px] text-muted">
                      {languageName(result.language)} · flagged at{" "}
                      <span className="tabular-nums">{result.threshold}%</span>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
