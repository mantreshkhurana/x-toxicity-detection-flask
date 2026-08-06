import type { Metadata } from "next";
import { AlertIcon } from "@/components/icons";
import { ModelCard } from "@/components/model-card";
import { Columns, ColumnHeader, RailFooter } from "@/components/shell";
import { fetchModelInfo } from "@/lib/api";
import { languageName } from "@/lib/format";

export const metadata: Metadata = {
  title: "Model card · X Toxicity Detection",
  description: "How the multilingual toxicity model is built and measured.",
};

const PIPELINE = [
  {
    title: "Normalization",
    body: "Unicode NFKC, invisible and bidi characters stripped, URLs and mentions removed, hashtags unwrapped. Then de-obfuscation: repeated letters, interior leetspeak, censoring symbols, spaced-out letters, and Cyrillic look-alikes folded back to Latin.",
  },
  {
    title: "Features",
    body: "Word 1-2 grams plus character 2-5 grams. The character half is what makes a single model work across 50+ languages — it handles agglutinative morphology, unsegmented scripts, and misspellings that word tokens miss.",
  },
  {
    title: "Classifier",
    body: "A soft-voting ensemble of three linear models: logistic regression, a calibrated linear SVM, and modified-Huber SGD. They fail on different examples, so the average beats every member.",
  },
  {
    title: "Per-language thresholds",
    body: "The cut-off is tuned separately per language on a validation split. One global threshold systematically over-flags the languages the model is least sure about.",
  },
];

export default async function ModelPage() {
  const model = await fetchModelInfo();

  return (
    <Columns
      rail={
        <>
          <ModelCard model={model} />
          <RailFooter />
        </>
      }
    >
      <ColumnHeader title="Model card" subtitle="How the score is produced" backHref="/" />

      <section className="border-b border-line px-4 py-5">
        <h2 className="mb-3 text-[20px] font-extrabold">Pipeline</h2>
        <ol className="flex flex-col gap-4">
          {PIPELINE.map((step, index) => (
            <li key={step.title}>
              <h3 className="text-[15px] font-bold">
                {index + 1}. {step.title}
              </h3>
              <p className="mt-0.5 text-[15px] leading-6 text-muted">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-b border-line px-4 py-5">
        <h2 className="mb-3 text-[20px] font-extrabold">
          Languages{model ? ` (${model.languages.length})` : ""}
        </h2>
        {model ? (
          <ul className="flex flex-wrap gap-1.5">
            {model.languages.map((code) => (
              <li
                key={code}
                className="rounded-full bg-raised px-3 py-1 text-[13px] text-muted"
              >
                <span className="font-bold text-ink uppercase">{code}</span>{" "}
                {languageName(code)}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[15px] text-muted">
            Start the analysis service to load the language list.
          </p>
        )}
        <p className="mt-3 text-[15px] leading-6 text-muted">
          Text in a language with no training data still gets scored — character
          n-grams generalize across related languages — it just gets the global
          threshold instead of a tuned one.
        </p>
      </section>

      <section className="px-4 py-5">
        <div className="rounded-2xl border border-toxic/40 bg-toxic-soft p-4">
          <h2 className="flex items-center gap-2 text-[15px] font-bold text-toxic">
            <AlertIcon className="h-5 w-5" />
            Why there is no 100%
          </h2>
          <p className="mt-2 text-[15px] leading-6">
            Toxicity is a judgement call, not a fact. Annotators on these datasets
            disagree with each other a meaningful share of the time; sarcasm and
            reclaimed slurs invert the label depending on who is speaking; the same
            sentence can be a joke between friends or harassment from a stranger. A
            model cannot be more consistent than the labels it learned from, so any
            toxicity classifier claiming perfect accuracy is reporting its training
            error. Treat the score as a ranking signal for human review.
          </p>
        </div>
      </section>
    </Columns>
  );
}
