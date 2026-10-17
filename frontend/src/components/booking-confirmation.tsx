"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CalendarDays, Check, CircleHelp, Clock3, Gamepad2 } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useSyncExternalStore } from "react";
import { getBooking, requestJson } from "@/lib/api";

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

function getAccessToken() {
  return window.sessionStorage.getItem("cyberbook.access") ?? "";
}

function bookingDate(value: string) {
  return new Intl.DateTimeFormat("en", { dateStyle: "full", timeStyle: "short" }).format(new Date(value));
}

export function BookingConfirmation({ bookingId }: { bookingId: string }) {
  const queryClient = useQueryClient();
  const token = useSyncExternalStore(subscribe, getAccessToken, () => "");
  const query = useQuery({ queryKey: ["booking", bookingId, token], queryFn: () => getBooking(bookingId, token), enabled: Boolean(token) });
  const cancelMutation = useMutation({
    mutationFn: () => requestJson(`/bookings/${bookingId}/cancel`, {}, token),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["booking", bookingId] });
      await queryClient.invalidateQueries({ queryKey: ["bookings"] });
    },
  });
  const booking = query.data;

  if (!token) return <main className="booking-not-found"><CircleHelp size={22} /><h1>Sign in to view this booking.</h1><Link href="/login">Sign in <ArrowRight size={15} /></Link></main>;
  if (query.isPending) return <main className="detail-loading"><span className="loading-line" /> Loading booking</main>;
  if (query.isError || !booking) return <main className="booking-not-found"><CircleHelp size={22} /><h1>Booking unavailable.</h1><p>{query.error?.message}</p><Link href="/bookings">Your bookings <ArrowRight size={15} /></Link></main>;

  const cancellable = booking.status === "PENDING" || booking.status === "CONFIRMED";
  return <main className="confirmation-page"><header className="detail-top"><Link className="brand" href="/"><span className="brand-mark"><Gamepad2 size={17} /></span><span>cyber<span>book</span></span></Link><Link className="back-link" href="/bookings"><ArrowLeft size={15} /> All bookings</Link></header>
    <section className="confirmation-wrap"><div className="confirmation-overline"><span className="confirmation-check"><Check size={18} /></span><div><div className="eyebrow">BOOKING CONFIRMED</div><p>Your session is on the calendar.</p></div></div>
      <div className="confirmation-grid"><article className="confirmation-details"><div className="eyebrow">BOOKING / {booking.id.slice(0, 8).toUpperCase()}</div><h1>Ready when<br /><em>you are.</em></h1><div className="confirmation-fact"><CalendarDays size={16} /><span><small>STARTS</small>{bookingDate(booking.start_time)}</span></div><div className="confirmation-fact"><Clock3 size={16} /><span><small>ENDS</small>{bookingDate(booking.end_time)}</span></div><div className="confirmation-summary"><span>Computer ID</span><strong>{booking.computer_id.slice(0, 8)}</strong><span>Status</span><strong>{booking.status}</strong><span>Total</span><strong>{Number(booking.total_price).toLocaleString("en-US")} KZT</strong></div>
        {cancelMutation.isError && <p className="form-error" role="alert">{cancelMutation.error.message}</p>}{cancelMutation.isSuccess && <p className="form-error">Booking cancelled.</p>}
        <div className="confirmation-actions"><Link href="/bookings">View all bookings <ArrowRight size={15} /></Link>{cancellable && <button type="button" onClick={() => cancelMutation.mutate()} disabled={cancelMutation.isPending}>{cancelMutation.isPending ? "Cancelling..." : "Cancel booking"}</button>}</div>
      </article><aside className="qr-panel"><div className="eyebrow">YOUR CHECK-IN PASS</div><div className="qr-surface"><QRCodeSVG value={booking.qr_token} size={190} level="M" includeMargin /></div><strong>Show this code at the club.</strong><p>It contains a private booking token. Keep it to yourself until check-in.</p><span className="qr-reference">REF / {booking.id.slice(0, 12).toUpperCase()}</span></aside></div>
    </section>
  </main>;
}