import type { Metadata } from "next";
import { Analyzer } from "@/components/analyzer";
import { ModelCard } from "@/components/model-card";
import { Columns, ColumnHeader, RailFooter } from "@/components/shell";
import { fetchModelInfo } from "@/lib/api";

export const metadata: Metadata = {
  title: "Analyze text · X Toxicity Detection",
  description: "Score any text for toxicity in 56 languages.",
};

export default async function AnalyzePage() {
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
      <ColumnHeader
        title="Analyze text"
        subtitle="Any language, one post per line"
        backHref="/"
      />
      <Analyzer />
    </Columns>
  );
}
