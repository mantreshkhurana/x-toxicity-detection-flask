"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { normalizeHandle } from "@/lib/format";
import { SearchIcon } from "./icons";

const POST_COUNTS = [10, 20, 50];

/**
 * The one input this app has. Validation happens on submit (not per keystroke),
 * the error sits under the field it belongs to, and the button reports its own
 * pending state instead of leaving the user guessing.
 */
export function SearchForm({
  initialHandle = "",
  initialPosts = 20,
  autoFocus = false,
}: {
  initialHandle?: string;
  initialPosts?: number;
  autoFocus?: boolean;
}) {
  const router = useRouter();
  const [handle, setHandle] = useState(initialHandle);
  const [posts, setPosts] = useState(initialPosts);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const clean = normalizeHandle(handle);
    if (!clean) {
      setError("Enter an X username, for example @jack");
      return;
    }
    setError(null);
    setPending(true);
    router.push(`/u/${clean}?posts=${posts}`);
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3">
      <div>
        <label htmlFor="handle" className="mb-1.5 block text-[13px] font-medium text-muted">
          X username
        </label>
        <div className="flex items-center gap-2 rounded-full border border-line bg-raised px-4 transition-colors duration-200 focus-within:border-brand">
          <SearchIcon className="h-[18px] w-[18px] text-muted" />
          <span className="text-[17px] text-muted select-none">@</span>
          <input
            id="handle"
            name="handle"
            value={handle}
            autoFocus={autoFocus}
            autoComplete="off"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            enterKeyHint="search"
            placeholder="username"
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "handle-error" : "handle-help"}
            onChange={(event) => {
              setHandle(event.target.value);
              if (error) setError(null);
            }}
            className="h-12 w-full min-w-0 bg-transparent text-[17px] outline-none placeholder:text-muted"
          />
        </div>
        {error ? (
          <p id="handle-error" role="alert" className="mt-1.5 text-[13px] text-toxic">
            {error}
          </p>
        ) : (
          <p id="handle-help" className="mt-1.5 text-[13px] text-muted">
            Public accounts only. Nothing is stored.
          </p>
        )}
      </div>

      <fieldset>
        <legend className="mb-1.5 text-[13px] font-medium text-muted">
          Posts to analyze
        </legend>
        <div className="flex gap-2">
          {POST_COUNTS.map((count) => (
            <button
              key={count}
              type="button"
              aria-pressed={posts === count}
              onClick={() => setPosts(count)}
              className={`h-11 min-w-[64px] cursor-pointer rounded-full border px-4 text-[15px] font-bold tabular-nums transition-colors duration-200 ${
                posts === count
                  ? "border-brand bg-brand text-white"
                  : "border-line text-ink hover:bg-hover"
              }`}
            >
              {count}
            </button>
          ))}
        </div>
      </fieldset>

      <button
        type="submit"
        disabled={pending}
        className="mt-1 flex h-12 cursor-pointer items-center justify-center gap-2 rounded-full bg-brand text-[15px] font-bold text-white transition-colors duration-200 hover:bg-brand-hover disabled:cursor-progress disabled:opacity-60"
      >
        {pending && (
          <span
            aria-hidden="true"
            className="spin h-4 w-4 rounded-full border-2 border-white/40 border-t-white"
          />
        )}
        {pending ? "Analyzing…" : "Analyze profile"}
      </button>
    </form>
  );
}
