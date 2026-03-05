import ProgrammeDetailPage from "./ProgrammeClient";

export async function generateStaticParams() {
  return [{ programmeId: "_" }];
}

export default function Page() {
  return <ProgrammeDetailPage />;
}
