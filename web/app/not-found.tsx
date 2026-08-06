import Link from "next/link";
import { Columns, ColumnHeader, RailFooter } from "@/components/shell";
import { SearchIcon } from "@/components/icons";

export default function NotFound() {
  return (
    <Columns rail={<RailFooter />}>
      <ColumnHeader title="Not found" backHref="/" />
      <div className="flex flex-col items-center gap-3 px-8 py-16 text-center">
        <SearchIcon className="h-8 w-8 text-muted" />
        <h2 className="text-[20px] font-extrabold">This page doesn&apos;t exist</h2>
        <p className="max-w-[380px] text-[15px] leading-6 text-muted">
          Check the URL, or head back and analyze a profile.
        </p>
        <Link
          href="/"
          className="mt-2 flex h-11 cursor-pointer items-center rounded-full bg-brand px-5 text-[15px] font-bold text-white transition-colors duration-200 hover:bg-brand-hover"
        >
          Go home
        </Link>
      </div>
    </Columns>
  );
}
