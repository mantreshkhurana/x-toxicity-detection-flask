"use client";

import { useMemo, useState } from "react";
import type { Post, ProfileUser } from "@/lib/types";
import { ShieldIcon } from "./icons";
import { TweetCard } from "./tweet-card";

type Tab = "all" | "toxic" | "safe";

const TABS: { id: Tab; label: string }[] = [
  { id: "all", label: "Posts" },
  { id: "toxic", label: "Flagged" },
  { id: "safe", label: "Safe" },
];

/**
 * X's underlined tab bar. Filtering is local state — the posts are already
 * scored, so switching tabs costs nothing and never refetches.
 */
export function Timeline({
  posts,
  user,
}: {
  posts: Post[];
  user: ProfileUser;
}) {
  const [tab, setTab] = useState<Tab>("all");

  const counts = useMemo(
    () => ({
      all: posts.length,
      toxic: posts.filter((post) => post.toxicity.is_toxic).length,
      safe: posts.filter((post) => !post.toxicity.is_toxic).length,
    }),
    [posts],
  );

  const visible = useMemo(() => {
    if (tab === "toxic") return posts.filter((post) => post.toxicity.is_toxic);
    if (tab === "safe") return posts.filter((post) => !post.toxicity.is_toxic);
    return posts;
  }, [posts, tab]);

  return (
    <>
      <div role="tablist" aria-label="Filter posts" className="flex border-b border-line">
        {TABS.map(({ id, label }) => {
          const active = tab === id;
          return (
            <button
              key={id}
              role="tab"
              type="button"
              aria-selected={active}
              aria-controls="timeline-panel"
              onClick={() => setTab(id)}
              className={`relative flex-1 cursor-pointer px-4 py-4 text-[15px] transition-colors duration-200 hover:bg-hover ${
                active ? "font-bold text-ink" : "text-muted"
              }`}
            >
              {label}
              <span className="ml-1.5 tabular-nums">{counts[id]}</span>
              {active && (
                <span className="absolute inset-x-0 bottom-0 mx-auto h-1 w-14 rounded-full bg-brand" />
              )}
            </button>
          );
        })}
      </div>

      <div id="timeline-panel" role="tabpanel">
        {visible.length === 0 ? (
          <EmptyState tab={tab} />
        ) : (
          visible.map((post, index) => (
            <TweetCard key={post.id || index} post={post} user={user} index={index} />
          ))
        )}
      </div>
    </>
  );
}

function EmptyState({ tab }: { tab: Tab }) {
  const copy =
    tab === "toxic"
      ? {
          title: "Nothing flagged",
          body: "No post in this sample crossed the threshold for its language.",
        }
      : tab === "safe"
        ? {
            title: "Every post was flagged",
            body: "All posts in this sample scored above the threshold for their language.",
          }
        : {
            title: "No posts",
            body: "This account has no recent public posts to analyze.",
          };

  return (
    <div className="flex flex-col items-center gap-2 px-8 py-16 text-center">
      <ShieldIcon className="h-8 w-8 text-muted" />
      <h2 className="text-[20px] font-extrabold">{copy.title}</h2>
      <p className="max-w-[380px] text-[15px] leading-6 text-muted">{copy.body}</p>
    </div>
  );
}
