import { PaymentStatusPage } from "@/components/payment-status-page";

export default async function PaymentPage({ params }: PageProps<"/payments/[id]">) {
  const { id } = await params;
  return <PaymentStatusPage paymentId={id} />;
}
