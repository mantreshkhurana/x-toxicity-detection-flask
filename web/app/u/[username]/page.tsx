import type { Metadata } from "next";
import Link from "next/link";
import { AlertIcon } from "@/components/icons";
import { ModelCard } from "@/components/model-card";
import { ProfileHeader } from "@/components/profile-header";
import { SearchForm } from "@/components/search-form";
import { Columns, ColumnHeader, RailCard, RailFooter } from "@/components/shell";
import { Timeline } from "@/components/timeline";
import { ScoreMeter } from "@/components/toxicity-badge";
import { LanguageBreakdown, ToxicityDonut } from "@/components/toxicity-donut";
import { ApiError, fetchProfile } from "@/lib/api";
import { normalizeHandle } from "@/lib/format";

type PageProps = {
  params: Promise<{ username: string }>;
  searchParams: Promise<{ posts?: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { username } = await params;
  return {
    title: `@${normalizeHandle(username)} · X Toxicity Detection`,
  };
}

function parsePostCount(raw: string | undefined) {
  const parsed = Number.parseInt(raw ?? "20", 10);
  if (Number.isNaN(parsed)) return 20;
  return Math.min(Math.max(parsed, 1), 100);
}

export default async function ProfilePage({ params, searchParams }: PageProps) {
  const { username } = await params;
  const { posts: postsParam } = await searchParams;
  const handle = normalizeHandle(username);
  const count = parsePostCount(postsParam);

  let data;
  try {
    data = await fetchProfile(handle, count);
  } catch (error) {
    const message =
      error instanceof ApiError ? error.message : "Something went wrong.";
    return <ProfileError handle={handle} message={message} />;
  }

  const { user, summary, model, posts } = data;

  return (
    <Columns
      rail={
        <>
          <RailCard title="Toxicity">
            <ToxicityDonut summary={summary} />
            <div className="mt-5 flex flex-col gap-4">
              <ScoreMeter
                label="Average score"
                value={summary.average_score}
                tone={summary.average_score >= 50 ? "toxic" : "brand"}
              />
              <ScoreMeter
                label="Flagged share"
                value={summary.toxic_ratio}
                tone="toxic"
              />
            </div>
          </RailCard>

          <RailCard title="Languages">
            <LanguageBreakdown summary={summary} />
          </RailCard>

          <ModelCard model={model} />
          <RailFooter />
        </>
      }
    >
      <ColumnHeader
        title={user.name}
        subtitle={`${summary.total} posts analyzed · ${summary.toxic_ratio}% toxic`}
        backHref="/"
      />

      <ProfileHeader user={user} summary={summary} />

      {/* the rail is hidden below lg, so the summary rides along in-column */}
      <section className="border-y border-line px-4 py-5 lg:hidden">
        <ToxicityDonut summary={summary} />
        <div className="mt-5">
          <LanguageBreakdown summary={summary} />
        </div>
      </section>

      <Timeline posts={posts} user={user} />

      <section className="px-4 py-6">
        <h2 className="mb-3 text-[15px] font-bold">Analyze another profile</h2>
        <SearchForm initialPosts={count} />
      </section>
    </Columns>
  );
}

function ProfileError({ handle, message }: { handle: string; message: string }) {
  return (
    <Columns rail={<RailFooter />}>
      <ColumnHeader title={`@${handle}`} backHref="/" />
      <div className="flex flex-col items-center gap-3 px-8 py-16 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-toxic-soft text-toxic">
          <AlertIcon className="h-6 w-6" />
        </span>
        <h2 className="text-[20px] font-extrabold">Couldn&apos;t analyze @{handle}</h2>
        <p className="max-w-[420px] text-[15px] leading-6 text-muted">{message}</p>
        <div className="mt-2 flex gap-2">
          <Link
            href={`/u/${handle}`}
            className="flex h-11 cursor-pointer items-center rounded-full bg-brand px-5 text-[15px] font-bold text-white transition-colors duration-200 hover:bg-brand-hover"
          >
            Try again
          </Link>
          <Link
            href="/"
            className="flex h-11 cursor-pointer items-center rounded-full border border-line px-5 text-[15px] font-bold transition-colors duration-200 hover:bg-hover"
          >
            Search another
          </Link>
        </div>
      </div>
    </Columns>
  );
}
