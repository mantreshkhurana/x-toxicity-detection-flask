"use client";

import Image from "next/image";
import { useState } from "react";
import { absoluteTime, compactNumber, relativeTime } from "@/lib/format";
import type { Post, ProfileUser } from "@/lib/types";
import {
  LikeIcon,
  ReplyIcon,
  RepostIcon,
  ShareIcon,
  VerifiedIcon,
} from "./icons";
import { LanguageBadge, ToxicityBadge } from "./toxicity-badge";

const URL_PATTERN = /(https?:\/\/[^\s]+)/g;

/** Links, @mentions and #hashtags get X's blue; everything else is plain text. */
function RichText({ text }: { text: string }) {
  const segments = text.split(URL_PATTERN);
  return (
    <>
      {segments.map((segment, index) => {
        if (index % 2 === 1) {
          return (
            <a
              key={index}
              href={segment}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="cursor-pointer text-brand hover:underline"
              onClick={(event) => event.stopPropagation()}
            >
              {segment.replace(/^https?:\/\//, "").slice(0, 32)}
              {segment.length > 39 ? "…" : ""}
            </a>
          );
        }
        return (
          <span key={index}>
            {segment.split(/(\s+)/).map((word, wordIndex) => {
              if (/^[@#]\w+$/.test(word)) {
                return (
                  <span key={wordIndex} className="text-brand">
                    {word}
                  </span>
                );
              }
              return <span key={wordIndex}>{word}</span>;
            })}
          </span>
        );
      })}
    </>
  );
}

function ActionButton({
  label,
  count,
  tone,
  children,
}: {
  label: string;
  count?: number;
  tone: "brand" | "safe" | "toxic";
  children: React.ReactNode;
}) {
  const hover =
    tone === "safe"
      ? "group-hover/action:bg-safe-soft group-hover/action:text-safe"
      : tone === "toxic"
        ? "group-hover/action:bg-toxic-soft group-hover/action:text-toxic"
        : "group-hover/action:bg-brand-soft group-hover/action:text-brand";

  return (
    <span className="group/action flex cursor-pointer items-center text-muted transition-colors duration-200">
      <span
        aria-hidden="true"
        className={`flex h-9 w-9 items-center justify-center rounded-full transition-colors duration-200 ${hover}`}
      >
        {children}
      </span>
      <span className="text-[13px] tabular-nums">
        {count !== undefined ? compactNumber(count) : ""}
      </span>
      <span className="sr-only">{label}</span>
    </span>
  );
}

export function TweetCard({
  post,
  user,
  index = 0,
}: {
  post: Post;
  user: ProfileUser;
  index?: number;
}) {
  const [avatarFailed, setAvatarFailed] = useState(false);
  const avatar = avatarFailed
    ? `https://unavatar.io/twitter/${user.screen_name}`
    : user.avatar;

  return (
    <article
      className="fade-rise relative flex gap-3 border-b border-line px-4 py-3 transition-colors duration-200 hover:bg-hover"
      style={{ animationDelay: `${Math.min(index, 12) * 30}ms` }}
    >
      {/* the toxic accent bar reads at a glance without relying on hue alone */}
      {post.toxicity.is_toxic && (
        <span aria-hidden="true" className="absolute inset-y-0 left-0 w-[3px] bg-toxic" />
      )}

      <a
        href={`https://x.com/${user.screen_name}`}
        target="_blank"
        rel="noopener noreferrer"
        className="shrink-0 cursor-pointer"
        aria-label={`${user.name} on X`}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={avatar}
          alt=""
          width={48}
          height={48}
          loading="lazy"
          onError={() => setAvatarFailed(true)}
          className="h-12 w-12 rounded-full object-cover"
        />
      </a>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-1.5 text-[15px] leading-5">
          <span className="truncate font-bold hover:underline">{user.name}</span>
          <VerifiedIcon className="h-[18px] w-[18px] text-brand" />
          <span className="truncate text-muted">@{user.screen_name}</span>
          <span className="text-muted" aria-hidden="true">·</span>
          <time
            dateTime={post.created_at}
            title={absoluteTime(post.created_at)}
            className="text-muted hover:underline"
          >
            {relativeTime(post.created_at)}
          </time>
        </div>

        <p className="mt-0.5 text-[15px] leading-6 whitespace-pre-wrap break-words">
          <RichText text={post.text} />
        </p>

        {post.media.length > 0 && (
          <div
            className={`mt-3 grid gap-0.5 overflow-hidden rounded-2xl border border-line ${
              post.media.length > 1 ? "grid-cols-2" : "grid-cols-1"
            }`}
          >
            {post.media.slice(0, 4).map((media) => (
              <Image
                key={media.url}
                src={media.url}
                alt="Media attached to this post"
                width={600}
                height={400}
                unoptimized
                loading="lazy"
                className="h-full max-h-[280px] w-full object-cover"
              />
            ))}
          </div>
        )}

        <div className="mt-3 flex max-w-[425px] items-center justify-between">
          <ActionButton label="Replies" tone="brand">
            <ReplyIcon />
          </ActionButton>
          <ActionButton label="Reposts" count={post.retweet_count} tone="safe">
            <RepostIcon />
          </ActionButton>
          <ActionButton label="Likes" count={post.favorite_count} tone="toxic">
            <LikeIcon />
          </ActionButton>
          <a
            href={post.url}
            target="_blank"
            rel="noopener noreferrer"
            className="group/action flex cursor-pointer items-center text-muted"
            aria-label="Open this post on X"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-full transition-colors duration-200 group-hover/action:bg-brand-soft group-hover/action:text-brand">
              <ShareIcon />
            </span>
          </a>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2">
          <ToxicityBadge toxicity={post.toxicity} />
          <LanguageBadge code={post.toxicity.language} />
        </div>
      </div>
    </article>
  );
}
