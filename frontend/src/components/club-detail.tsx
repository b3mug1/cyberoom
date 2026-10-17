"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CalendarDays, Check, Clock3, Cpu, MapPin, Monitor, MonitorCog, ShieldCheck } from "lucide-react";
import { useMemo, useState, useSyncExternalStore } from "react";

import { getClub, requestJson } from "@/lib/api";
import type { Computer } from "@/types/api";

type Quote = { total_price: string; currency: string };
type Booking = { id: string };

function localDate(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function localIso(date: string, time: string) {
  return new Date(`${date}T${time}:00`).toISOString();
}

function subscribeToSession(callback: () => void) {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

function hasActiveSession() {
  return Boolean(window.sessionStorage.getItem("cyberbook.access"));
}

function ComputerRow({ computer, selected, onSelect }: { computer: Computer; selected: boolean; onSelect: () => void }) {
  const available = computer.is_active && computer.status === "AVAILABLE";
  return <button type="button" className={`computer-row${selected ? " computer-selected" : ""}`} onClick={onSelect} disabled={!available} aria-pressed={selected}>
    <span className="computer-radio">{selected && <Check size={13} />}</span>
    <span className="computer-main"><strong>{computer.name}</strong><small>{computer.gpu} · {computer.ram_gb} GB RAM</small></span>
    <span className="computer-sub"><Cpu size={13} />{computer.cpu}</span>
    <span className="computer-sub"><Monitor size={13} />{computer.refresh_rate} Hz</span>
    <span className={`computer-status ${available ? "is-available" : ""}`}>{available ? "Available" : computer.status.toLowerCase()}</span>
  </button>;
}

export function ClubDetail({ clubId }: { clubId: string }) {
  const router = useRouter();
  const clubQuery = useQuery({ queryKey: ["club", clubId], queryFn: () => getClub(clubId) });
  const club = clubQuery.data;
  const [computerId, setComputerId] = useState("");
  const [sessionDate, setSessionDate] = useState(() => localDate(new Date(Date.now() + 86_400_000)));
  const [startTime, setStartTime] = useState("18:00");
  const [endTime, setEndTime] = useState("20:00");
  const signedIn = useSyncExternalStore(subscribeToSession, hasActiveSession, () => false);

  const interval = useMemo(() => {
    if (!sessionDate || !startTime || !endTime || startTime >= endTime) return null;
    const start = localIso(sessionDate, startTime);
    const end = localIso(sessionDate, endTime);
    return { start_time: start, end_time: end };
  }, [sessionDate, startTime, endTime]);

  const quoteQuery = useQuery({
    queryKey: ["booking-quote", computerId, interval],
    queryFn: () => requestJson<Quote>("/bookings/quote", { computer_id: computerId, ...interval }),
    enabled: Boolean(computerId && interval),
    retry: false,
  });

  const bookingMutation = useMutation({
    mutationFn: async () => {
      const accessToken = sessionStorage.getItem("cyberbook.access");
      if (!accessToken) throw new Error("Sign in to confirm your booking.");
      return requestJson<Booking>("/bookings", { computer_id: computerId, ...interval }, accessToken);
    },
    onSuccess: (booking) => router.push(`/booking/${booking.id}`),
  });

  if (clubQuery.isPending) return <main className="detail-loading"><span className="loading-line" /> Loading club details</main>;
  if (clubQuery.isError || !club) return <main className="detail-error"><h1>Club unavailable</h1><p>{clubQuery.error?.message ?? "We couldn't load this club."}</p><Link href="/">Back to clubs <ArrowRight size={15} /></Link></main>;

  const selectedComputer = club.computers.find((computer) => computer.id === computerId);
  const availableComputers = club.computers.filter((computer) => computer.is_active && computer.status === "AVAILABLE");

  return <main className="detail-page">
    <header className="detail-top"><Link className="brand" href="/"><span className="brand-mark">CB</span><span>cyber<span>book</span></span></Link><Link className="back-link" href="/"><ArrowLeft size={15} /> All clubs</Link><Link className="detail-account" href={signedIn ? "/bookings" : "/login"}>{signedIn ? "My bookings" : "Sign in"}</Link></header>
    <section className="club-detail-hero">
      <div className="club-detail-photo"><Image fill priority sizes="100vw" src="https://images.unsplash.com/photo-1542751371-adc38448a05e?auto=format&fit=crop&w=1800&q=90" alt={`${club.name} gaming floor`} /><span className="photo-caption"><span className="live-dot" /> CLUB / {club.city.toUpperCase()}</span><span className="photo-index">CB—{club.id.slice(0, 4).toUpperCase()}</span></div>
      <div className="club-detail-title"><div><div className="eyebrow"><MapPin size={13} /> {club.address} · {club.city}</div><h1>{club.name}</h1><p>{club.description}</p></div><div className="club-rating"><span>★</span>{Number(club.rating).toFixed(1)}<small>Club rating</small></div></div>
      <div className="club-facts"><span><ShieldCheck size={15} /> {availableComputers.length} PCs listed available</span><span><MonitorCog size={15} /> {club.computers.length} gaming stations</span><span><Clock3 size={15} /> Open daily</span><span>{club.phone}</span></div>
    </section>

    <section className="club-workspace">
      <div className="hardware-column"><div className="workspace-heading"><div><div className="eyebrow">CHOOSE YOUR STATION</div><h2>Find your rig.</h2></div><span>{availableComputers.length} available</span></div>
        <div className="computer-list">{club.computers.map((computer) => <ComputerRow key={computer.id} computer={computer} selected={computer.id === computerId} onSelect={() => setComputerId(computer.id)} />)}</div>
        <div className="tariff-list"><div className="eyebrow">HOURLY TARIFFS</div>{club.tariffs.map((tariff) => <div className="tariff-row" key={tariff.id}><span>{tariff.name}</span><span>{tariff.start_time.slice(0, 5)}–{tariff.end_time.slice(0, 5)}</span><strong>{Number(tariff.price_per_hour).toLocaleString("en-US")} KZT / HR</strong></div>)}</div>
      </div>

      <aside className="booking-panel"><div className="eyebrow">MAKE IT A SESSION <span>01 / 03</span></div><h2>Book a station.</h2><p className="booking-intro">Choose a time and we’ll calculate the exact price from the club’s tariffs.</p>
        <label className="booking-label">DATE<div className="input-wrap"><CalendarDays size={16} /><input type="date" min={localDate(new Date())} value={sessionDate} onChange={(event) => setSessionDate(event.target.value)} /></div></label>
        <div className="time-grid"><label className="booking-label">START<div className="input-wrap"><Clock3 size={15} /><input type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} /></div></label><label className="booking-label">END<div className="input-wrap"><Clock3 size={15} /><input type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} /></div></label></div>
        <label className="booking-label">COMPUTER<div className="selected-computer">{selectedComputer ? <><span>{selectedComputer.name}</span><small>{selectedComputer.gpu}</small></> : <span>Select a computer from the list</span>}</div></label>
        <div className="quote-row"><span>Estimated total</span><strong>{quoteQuery.isFetching ? "Calculating..." : quoteQuery.data ? `${Number(quoteQuery.data.total_price).toLocaleString("en-US")} ${quoteQuery.data.currency}` : "— KZT"}</strong></div>
        {quoteQuery.isError && <p className="form-error" role="alert">{quoteQuery.error.message}</p>}
        {bookingMutation.isError && <p className="form-error" role="alert">{bookingMutation.error.message}</p>}
        {!interval && <p className="form-hint">Choose a future date and a valid same-day time range.</p>}
        <button className="confirm-booking" type="button" disabled={!computerId || !interval || quoteQuery.isError || !quoteQuery.data || bookingMutation.isPending} onClick={() => bookingMutation.mutate()}>{bookingMutation.isPending ? "Confirming..." : signedIn ? "Confirm booking" : "Sign in to book"}<ArrowRight size={16} /></button>
        {!signedIn && <p className="auth-hint">You’ll need an account to confirm your booking. <Link href="/login">Sign in</Link></p>}
      </aside>
    </section>
  </main>;
}