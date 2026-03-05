import CourseDetailPage from "./CourseClient";

export async function generateStaticParams() {
  return [{ courseId: "_" }];
}

export default function Page() {
  return <CourseDetailPage />;
}
