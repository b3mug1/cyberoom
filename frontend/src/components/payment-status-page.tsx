"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CircleHelp } from "lucide-react";
import { useSyncExternalStore } from "react";

import { Brand } from "@/components/brand";
import { getAccessToken, subscribeToAuth } from "@/lib/auth-session";
import { authenticatedRequest } from "@/lib/api";
import type { Payment } from "@/types/api";

export function PaymentStatusPage({ paymentId }: { paymentId: string }) {
  const token = useSyncExternalStore(subscribeToAuth, getAccessToken, () => "");
  const query = useQuery({
    queryKey: ["payment", paymentId, token],
    queryFn: () => authenticatedRequest<Payment>(`/payments/${paymentId}`, token, "GET"),
    enabled: Boolean(token),
    refetchInterval: (current) => ["PAID", "FAILED", "REFUNDED"].includes(current.state.data?.status ?? "") ? false : 5000,
  });
  const payment = query.data;
  const complete = payment?.status === "PAID";

  return <main className="payment-status-page"><header className="detail-top"><Brand size="md" /><Link className="back-link" href="/profile"><ArrowLeft size={15} /> Profile</Link></header><section className="payment-status-card">
    <div className="eyebrow">PAYMENT / {paymentId.slice(0, 8).toUpperCase()}</div>
    {!token ? <><CircleHelp size={24} /><h1>Sign in to check this payment.</h1><Link href="/login">Sign in <ArrowRight size={15} /></Link></> : query.isPending ? <><h1>Checking payment…</h1><p>We’re confirming the latest status with the payment provider.</p></> : query.isError ? <><h1>Payment status unavailable.</h1><p>{query.error.message}</p><Link href="/profile">Open profile <ArrowRight size={15} /></Link></> : payment ? <><h1>{complete ? "Payment complete." : payment.status === "FAILED" ? "Payment failed." : payment.status === "REFUNDED" ? "Payment refunded." : payment.status === "REFUND_PENDING" ? "Refund is processing." : "Payment is processing."}</h1><p>{Number(payment.amount).toLocaleString("ru-RU")} {payment.currency} · {payment.status}</p>{Number(payment.refund_amount) > 0 && <p>Refund: {Number(payment.refund_amount).toLocaleString("ru-RU")} {payment.currency}</p>}<div className="payment-status-links">{payment.booking_id && <Link href={`/booking/${payment.booking_id}`}>View booking <ArrowRight size={15} /></Link>}<Link href={complete && payment.membership_plan_id ? "/profile" : "/bookings"}>{payment.membership_plan_id ? "View memberships" : "My bookings"} <ArrowRight size={15} /></Link></div></> : null}
  </section></main>;
}
