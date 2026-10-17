import { BookingConfirmation } from "@/components/booking-confirmation";

export default async function BookingPage({ params }: PageProps<"/booking/[id]">) {
  const { id } = await params;
  return <BookingConfirmation bookingId={id} />;
}