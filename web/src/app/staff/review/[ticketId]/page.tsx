import ReviewTicketPage from "./ReviewClient";

export async function generateStaticParams() {
  return [{ ticketId: "_" }];
}

export default function Page() {
  return <ReviewTicketPage />;
}
