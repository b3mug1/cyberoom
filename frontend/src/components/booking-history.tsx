"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CalendarDays, CircleHelp } from "lucide-react";
import { useSyncExternalStore } from "react";
import { getBookings } from "@/lib/api";
import { Brand } from "@/components/brand";
import type { Booking } from "@/types/api";

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

function getAccessToken() {
  return window.sessionStorage.getItem("cyberoom.access") ?? "";
}

function bookingDate(value: string) {
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function BookingRow({ booking }: { booking: Booking }) {
  return <Link className="history-row" href={`/booking/${booking.id}`}><span className="history-date"><CalendarDays size={16} />{bookingDate(booking.start_time)}</span><span className="history-computer">Computer {booking.computer_id.slice(0, 8)}</span><span className={`status-pill status-${booking.status.toLowerCase()}`}>{booking.status}</span><strong>{Number(booking.total_price).toLocaleString("en-US")} KZT</strong><ArrowRight size={16} /></Link>;
}

export function BookingHistory() {
  const token = useSyncExternalStore(subscribe, getAccessToken, () => "");
  const query = useQuery({ queryKey: ["bookings", token], queryFn: () => getBookings(token), enabled: Boolean(token) });
  const bookings = query.data ?? [];

  return <main className="history-page"><header className="detail-top"><Brand size="md" /><Link className="back-link" href="/"><ArrowLeft size={15} /> Explore clubs</Link></header>
    <section className="history-content"><div className="eyebrow">PLAYER SPACE / BOOKINGS</div><h1>Your sessions.</h1><p className="history-lede">Every booking in one place, from confirmed sessions to past runs.</p>
      {!token && <div className="history-empty"><CircleHelp size={22} /><div><strong>Sign in to view your bookings.</strong><span>Your confirmed sessions will appear here.</span></div><Link href="/login">Sign in <ArrowRight size={15} /></Link></div>}
      {query.isPending && token && <div className="result-state"><div className="loading-line" /><span>Loading your sessions...</span></div>}
      {query.isError && <div className="history-empty"><CircleHelp size={22} /><div><strong>Bookings are unavailable.</strong><span>{query.error.message}</span></div></div>}
      {query.isSuccess && bookings.length === 0 && <div className="history-empty"><CalendarDays size={22} /><div><strong>No bookings yet.</strong><span>Pick a club and book your first session.</span></div><Link href="/">Explore clubs <ArrowRight size={15} /></Link></div>}
      {bookings.length > 0 && <div className="history-list">{bookings.map((booking) => <BookingRow key={booking.id} booking={booking} />)}</div>}
    </section>
  </main>;
}