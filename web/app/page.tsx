import Link from "next/link";
import { ModelCard } from "@/components/model-card";
import { SearchForm } from "@/components/search-form";
import { Columns, ColumnHeader, RailCard, RailFooter } from "@/components/shell";
import { LanguagesIcon, ShieldIcon, SparkIcon } from "@/components/icons";
import { fetchModelInfo } from "@/lib/api";

const SUGGESTIONS = ["jack", "elonmusk", "nasa", "bbcbreaking"];

const STEPS = [
  {
    icon: SparkIcon,
    title: "Fetch",
    body: "Posts come from X's public syndication endpoint. No API key, no login, nothing stored.",
  },
  {
    icon: LanguagesIcon,
    title: "Detect",
    body: "Each post's language is identified from its script and function words before it is scored.",
  },
  {
    icon: ShieldIcon,
    title: "Score",
    body: "A toxicity probability is compared against the threshold tuned for that specific language.",
  },
];

export default async function HomePage() {
  const model = await fetchModelInfo();

  return (
    <Columns
      rail={
        <>
          <ModelCard model={model} />
          <RailCard title="Try a profile">
            <ul className="flex flex-col">
              {SUGGESTIONS.map((handle) => (
                <li key={handle}>
                  <Link
                    href={`/u/${handle}`}
                    className="-mx-4 flex cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors duration-200 hover:bg-hover"
                  >
                    <span className="flex h-9 w-9 items-center justify-center rounded-full bg-hover text-[13px] font-bold uppercase">
                      {handle.slice(0, 2)}
                    </span>
                    <span className="text-[15px] font-bold">@{handle}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </RailCard>
          <RailFooter />
        </>
      }
    >
      <ColumnHeader title="Home" subtitle="Toxicity analysis for public X profiles" />

      <section className="border-b border-line px-4 py-6">
        <h2 className="text-[26px] leading-8 font-extrabold">
          How toxic is a timeline?
        </h2>
        <p className="mt-2 mb-6 text-[15px] leading-6 text-muted">
          Enter a username to score their recent posts in{" "}
          {model ? model.languages.length : 55}+ languages.
        </p>
        <SearchForm autoFocus />
      </section>

      <section className="border-b border-line px-4 py-5">
        <h2 className="mb-4 text-[20px] font-extrabold">How it works</h2>
        <ol className="flex flex-col gap-4">
          {STEPS.map(({ icon: Icon, title, body }, index) => (
            <li key={title} className="flex gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand">
                <Icon className="h-5 w-5" />
              </span>
              <div>
                <h3 className="text-[15px] font-bold">
                  {index + 1}. {title}
                </h3>
                <p className="text-[15px] leading-6 text-muted">{body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="px-4 py-5 lg:hidden">
        <ModelCard model={model} />
      </section>

      <section className="px-4 py-5">
        <div className="rounded-2xl border border-line p-4">
          <h2 className="text-[15px] font-bold">A score is not a verdict</h2>
          <p className="mt-1 text-[15px] leading-6 text-muted">
            Toxicity is a judgement call, and annotators disagree with each other
            often. Treat these numbers as a ranking signal for human review.{" "}
            <Link href="/model" className="cursor-pointer text-brand hover:underline">
              See the measured accuracy
            </Link>
            .
          </p>
        </div>
      </section>
    </Columns>
  );
}
