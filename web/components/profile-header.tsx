"use client";

import { useState } from "react";
import { compactNumber } from "@/lib/format";
import type { ProfileUser, Summary } from "@/lib/types";
import { VerifiedIcon } from "./icons";

/**
 * X's profile header: banner strip, avatar overlapping it, name block, then
 * counts. The toxicity summary line replaces the bio, which the syndication
 * endpoint does not return.
 */
export function ProfileHeader({
  user,
  summary,
}: {
  user: ProfileUser;
  summary: Summary;
}) {
  const [avatarFailed, setAvatarFailed] = useState(false);
  const avatar = avatarFailed
    ? `https://unavatar.io/twitter/${user.screen_name}`
    : user.avatar.replace("_normal", "_400x400");

  return (
    <section>
      <div
        aria-hidden="true"
        className="h-[140px] w-full bg-gradient-to-br from-brand/25 via-brand/10 to-transparent"
      />

      <div className="px-4 pb-3">
        <div className="-mt-14 mb-3 flex items-end justify-between gap-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={avatar}
            alt={`${user.name}'s profile picture`}
            width={112}
            height={112}
            onError={() => setAvatarFailed(true)}
            className="h-[112px] w-[112px] rounded-full border-4 border-canvas bg-canvas object-cover"
          />
          <a
            href={`https://x.com/${user.screen_name}`}
            target="_blank"
            rel="noopener noreferrer"
            className="mb-1 flex h-9 cursor-pointer items-center rounded-full border border-line px-4 text-[14px] font-bold transition-colors duration-200 hover:bg-hover"
          >
            View on X
          </a>
        </div>

        <div className="flex items-center gap-1">
          <h1 className="text-[20px] leading-6 font-extrabold">{user.name}</h1>
          <VerifiedIcon className="h-5 w-5 text-brand" />
        </div>
        <p className="text-[15px] text-muted">@{user.screen_name}</p>

        <p className="mt-3 text-[15px] leading-5">
          <span className="font-bold tabular-nums">{summary.toxic}</span>{" "}
          <span className="text-muted">
            of {summary.total} recent posts flagged toxic · average score{" "}
          </span>
          <span className="font-bold tabular-nums">{summary.average_score}%</span>
        </p>

        <dl className="mt-3 flex flex-wrap gap-x-5 text-[14px]">
          <div className="flex gap-1">
            <dt className="sr-only">Following</dt>
            <dd className="font-bold tabular-nums">
              {compactNumber(user.following_count)}
            </dd>
            <span className="text-muted">Following</span>
          </div>
          <div className="flex gap-1">
            <dt className="sr-only">Followers</dt>
            <dd className="font-bold tabular-nums">
              {compactNumber(user.followers_count)}
            </dd>
            <span className="text-muted">Followers</span>
          </div>
        </dl>
      </div>
    </section>
  );
}
