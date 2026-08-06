import Link from "next/link";
import { languageName } from "@/lib/format";
import type { ModelInfo } from "@/lib/types";

function percent(value: number | null | undefined) {
  return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
}

/**
 * Right-rail card in the shape of X's "What's happening" panel, carrying the
 * numbers that decide whether a score is worth trusting.
 */
export function ModelCard({ model }: { model: ModelInfo | null }) {
  if (!model) {
    return (
      <section className="rounded-2xl bg-raised p-4">
        <h2 className="text-xl font-extrabold">Model</h2>
        <p className="mt-2 text-[13px] text-muted">
          The analysis service is offline. Start it with{" "}
          <code className="rounded bg-hover px-1 py-0.5">python app.py</code>.
        </p>
      </section>
    );
  }

  const stats = [
    { label: "Accuracy", value: percent(model.accuracy) },
    { label: "Macro F1", value: percent(model.macro_f1) },
    { label: "ROC-AUC", value: percent(model.roc_auc) },
    {
      label: "Training posts",
      value: model.n_samples ? model.n_samples.toLocaleString() : "—",
    },
  ];

  return (
    <section className="rounded-2xl bg-raised">
      <h2 className="px-4 pt-3 pb-2 text-xl font-extrabold">Model</h2>

      <dl className="grid grid-cols-2 gap-px bg-line">
        {stats.map((stat) => (
          <div key={stat.label} className="bg-raised px-4 py-3">
            <dt className="text-[13px] text-muted">{stat.label}</dt>
            <dd className="text-[17px] font-bold tabular-nums">{stat.value}</dd>
          </div>
        ))}
      </dl>

      <div className="px-4 py-3">
        <p className="text-[13px] text-muted">
          {model.backend === "transformer" ? "Transformer" : "Linear ensemble"} ·{" "}
          {model.languages.length} languages
        </p>
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {model.languages.slice(0, 10).map((code) => (
            <li
              key={code}
              title={languageName(code)}
              className="rounded-full bg-hover px-2 py-0.5 text-[12px] font-medium text-muted uppercase"
            >
              {code}
            </li>
          ))}
          {model.languages.length > 10 && (
            <li className="rounded-full bg-hover px-2 py-0.5 text-[12px] font-medium text-muted">
              +{model.languages.length - 10}
            </li>
          )}
        </ul>
      </div>

      <Link
        href="/model"
        className="block cursor-pointer rounded-b-2xl px-4 py-3 text-[15px] text-brand transition-colors duration-200 hover:bg-hover"
      >
        How this is measured
      </Link>
    </section>
  );
}
