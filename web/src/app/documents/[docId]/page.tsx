import DocPage from "./DocPageClient";

export async function generateStaticParams() {
  return [{ docId: "_" }];
}

export default function Page() {
  return <DocPage />;
}
