import Link from "next/link";

export default function KpiCard({
  label,
  value,
  subtext,
  href,
}: {
  label: string;
  value: string;
  subtext?: string;
  href?: string;
}) {
  const inner = (
    <>
      <p className="text-sm text-neutral-500 dark:text-neutral-400">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
      {subtext && (
        <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{subtext}</p>
      )}
    </>
  );

  const className =
    "rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 transition-colors";

  if (href) {
    return (
      <Link href={href} className={`${className} hover:border-neutral-300 dark:hover:border-neutral-700 block`}>
        {inner}
      </Link>
    );
  }

  return <div className={className}>{inner}</div>;
}
