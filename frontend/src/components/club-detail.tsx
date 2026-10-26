"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CalendarDays, Check, Clock3, Cpu, MapPin, Monitor, MonitorCog, ShieldCheck } from "lucide-react";
import { useState, useSyncExternalStore } from "react";

import { apiBase, getClub, getClubMembershipPlans, getClubReviews, getMemberships, requestJson } from "@/lib/api";
import { clubDate, clubLocalToIso, nextClubDate } from "@/lib/club-time";
import { Brand } from "@/components/brand";
import type { ClubPriceMenu, Computer, MembershipPlan, Payment, WaitlistRequest } from "@/types/api";

type Quote = { total_price: string; subtotal_price: string; discount_amount: string; promo_code: string | null; membership_minutes: number; membership_credit_amount: string; currency: string };
type Booking = { id: string };
type Availability = { computers: Array<{ computer_id: string; busy: Array<{ start_time: string; end_time: string }> }> };

function subscribeToSession(callback: () => void) {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

function hasActiveSession() {
  return Boolean(window.sessionStorage.getItem("cyberoom.access"));
}

function ComputerRow({ computer, selected, onSelect }: { computer: Computer; selected: boolean; onSelect: () => void }) {
  const selectable = computer.is_active && !["MAINTENANCE", "DISABLED"].includes(computer.status);
  return <button type="button" className={`computer-row${selected ? " computer-selected" : ""}`} onClick={onSelect} disabled={!selectable} aria-pressed={selected}>
    <span className="computer-radio">{selected && <Check size={13} />}</span>
    <span className="computer-main"><strong>{computer.name}</strong><small>{computer.gpu} · {computer.ram_gb} GB RAM</small></span>
    <span className="computer-sub"><Cpu size={13} />{computer.cpu}</span>
    <span className="computer-sub"><Monitor size={13} />{computer.refresh_rate} Hz</span>
    <span className={`computer-status ${computer.status === "AVAILABLE" ? "is-available" : ""}`}>{computer.status === "AVAILABLE" ? "Available now" : computer.status === "OCCUPIED" ? "Occupied now" : computer.status.toLowerCase()}</span>
  </button>;
}

function PricePeriod({ label, pricing, currency }: {
  label: string;
  pricing: ClubPriceMenu["tiers"][number]["weekdays"];
  currency: string;
}) {
  const amount = (value: number) => `${value.toLocaleString("ru-RU")} ${currency}`;
  return <div className="bro-price-period">
    <h3>{label}</h3>
    <div className="bro-price-day"><span>День · {pricing.day_hours}</span><strong>{amount(pricing.day_price)}</strong></div>
    <div className="bro-price-line"><span>1 час</span><strong>{amount(pricing.hourly)}</strong></div>
    <div className="bro-price-deals">{pricing.deals.map((deal) => <span key={deal.label}>{deal.label} <strong>{amount(deal.price)}</strong></span>)}</div>
    <div className="bro-price-line"><span>Ночь · {pricing.night_hours}</span><strong>{amount(pricing.night_price)}</strong></div>
    <div className="bro-price-line"><span>Турбо ночь · {pricing.turbo_hours}</span><strong>{amount(pricing.turbo_price)}</strong></div>
  </div>;
}

function ClubPriceMenuView({ menu }: { menu: ClubPriceMenu }) {
  return <section className="bro-price-menu">
    <div className="bro-price-heading"><div><div className="eyebrow">BRO · PRICE LIST</div><h2>Прайс клуба</h2></div><span>Цены в {menu.currency}</span></div>
    <div className="bro-price-tiers">{menu.tiers.map((tier) => <article className="bro-price-tier" key={tier.name}>
      <h3>{tier.name}</h3>
      <div className="bro-price-periods">
        <PricePeriod label="Будни" pricing={tier.weekdays} currency={menu.currency} />
        <PricePeriod label="Выходные" pricing={tier.weekends} currency={menu.currency} />
      </div>
    </article>)}</div>
    <p className="bro-price-note">{menu.holiday_note} · «2+1» и «3+2» — стоимость пакета.</p>
  </section>;
}

export function ClubDetail({ clubId }: { clubId: string }) {
  const router = useRouter();
  const clubQuery = useQuery({ queryKey: ["club", clubId], queryFn: () => getClub(clubId) });
  const reviewsQuery = useQuery({ queryKey: ["club-reviews", clubId], queryFn: () => getClubReviews(clubId) });
  const membershipPlansQuery = useQuery({ queryKey: ["membership-plans", clubId], queryFn: () => getClubMembershipPlans(clubId) });
  const club = clubQuery.data;
  const [computerId, setComputerId] = useState("");
  const [sessionDate, setSessionDate] = useState("");
  const [today] = useState(() => new Date());
  const [startTime, setStartTime] = useState("18:00");
  const [endTime, setEndTime] = useState("20:00");
  const [promoCode, setPromoCode] = useState("");
  const [useMembership, setUseMembership] = useState(false);
  const signedIn = useSyncExternalStore(subscribeToSession, hasActiveSession, () => false);
  const membershipsQuery = useQuery({
    queryKey: ["memberships", clubId, signedIn],
    queryFn: () => getMemberships(sessionStorage.getItem("cyberoom.access") ?? ""),
    enabled: signedIn,
  });
  const clubTimezone = club?.timezone;
  const todayAtClub = clubTimezone ? clubDate(today, clubTimezone) : "";

  const selection = (() => {
    if (!clubTimezone || !sessionDate || !startTime || !endTime || startTime >= endTime) return { interval: null, error: null };
    try {
      return { interval: {
        start_time: clubLocalToIso(sessionDate, startTime, clubTimezone),
        end_time: clubLocalToIso(sessionDate, endTime, clubTimezone),
      }, error: null };
    } catch (error) {
      return { interval: null, error: error instanceof Error ? error.message : "Invalid club time." };
    }
  })();
  const interval = selection.interval;
  const dayRange = (() => {
    if (!clubTimezone || !sessionDate) return null;
    try {
      return {
        start_time: clubLocalToIso(sessionDate, "00:00", clubTimezone),
        end_time: clubLocalToIso(nextClubDate(sessionDate), "00:00", clubTimezone),
      };
    } catch { return null; }
  })();
  const availabilityQuery = useQuery({
    queryKey: ["club-availability", clubId, dayRange],
    queryFn: async () => {
      const params = new URLSearchParams(dayRange!);
      const response = await fetch(`${apiBase}/clubs/${clubId}/availability?${params}`, { cache: "no-store" });
      if (!response.ok) throw new Error("Could not load this club's reservations.");
      return response.json() as Promise<Availability>;
    },
    enabled: Boolean(dayRange),
    refetchInterval: 30_000,
  });
  const busy = availabilityQuery.data?.computers.find((computer) => computer.computer_id === computerId)?.busy ?? [];
  const hasConflict = Boolean(interval && busy.some((slot) => Date.parse(slot.start_time) < Date.parse(interval.end_time) && Date.parse(slot.end_time) > Date.parse(interval.start_time)));

  const quoteQuery = useQuery({
    queryKey: ["booking-quote", computerId, interval, promoCode.trim().toUpperCase(), useMembership],
    queryFn: () => requestJson<Quote>("/bookings/quote", {
      computer_id: computerId, ...interval,
      ...(promoCode.trim() ? { promo_code: promoCode.trim().toUpperCase() } : {}),
      use_membership: useMembership,
    }, signedIn ? sessionStorage.getItem("cyberoom.access") ?? undefined : undefined),
    enabled: Boolean(computerId && interval && !hasConflict),
    retry: false,
  });

  const bookingMutation = useMutation({
    mutationFn: async () => {
      const accessToken = sessionStorage.getItem("cyberoom.access");
      if (!accessToken) throw new Error("Sign in to confirm your booking.");
      return requestJson<Booking>("/bookings", {
        computer_id: computerId, ...interval,
        ...(promoCode.trim() ? { promo_code: promoCode.trim().toUpperCase() } : {}),
        use_membership: useMembership,
      }, accessToken);
    },
    onSuccess: (booking) => router.push(`/booking/${booking.id}`),
  });
  const waitlistMutation = useMutation({
    mutationFn: async () => {
      const accessToken = sessionStorage.getItem("cyberoom.access");
      if (!accessToken) throw new Error("Sign in to join the waitlist.");
      return requestJson<WaitlistRequest>("/waitlist", { club_id: clubId, start_time: interval!.start_time, end_time: interval!.end_time }, accessToken);
    },
  });
  const membershipPurchaseMutation = useMutation({
    mutationFn: async (plan: MembershipPlan) => {
      const accessToken = sessionStorage.getItem("cyberoom.access");
      if (!accessToken) throw new Error("Sign in to buy a membership.");
      return requestJson<Payment>(`/membership-plans/${plan.id}/checkout`, {}, accessToken);
    },
    onSuccess: (payment) => {
      if (payment.checkout_url) window.location.assign(payment.checkout_url);
    },
  });

  if (clubQuery.isPending) return <main className="detail-loading"><span className="loading-line" /> Loading club details</main>;
  if (clubQuery.isError || !club) return <main className="detail-error"><h1>Club unavailable</h1><p>{clubQuery.error?.message ?? "We couldn't load this club."}</p><Link href="/">Back to clubs <ArrowRight size={15} /></Link></main>;

  const selectedComputer = club.computers.find((computer) => computer.id === computerId);
  const availableComputers = club.computers.filter((computer) => computer.is_active && computer.status === "AVAILABLE");
  const bookableComputers = club.computers.filter((computer) => computer.is_active && !["DISABLED", "MAINTENANCE"].includes(computer.status));
  const hasMembershipHours = membershipsQuery.data?.some((item) => item.club_id === clubId && item.remaining_minutes > 0 && Date.parse(item.expires_at) > Date.now()) ?? false;
  const noComputersFree = Boolean(interval && availabilityQuery.isSuccess && bookableComputers.length > 0 && bookableComputers.every((computer) => {
    const slots = availabilityQuery.data?.computers.find((item) => item.computer_id === computer.id)?.busy ?? [];
    return slots.some((slot) => Date.parse(slot.start_time) < Date.parse(interval.end_time) && Date.parse(slot.end_time) > Date.parse(interval.start_time));
  }));

  return <main className="detail-page">
    <header className="detail-top"><Brand size="md" /><Link className="back-link" href="/"><ArrowLeft size={15} /> All clubs</Link><Link className="detail-account" href={signedIn ? "/bookings" : "/login"}>{signedIn ? "My bookings" : "Sign in"}</Link></header>
    <section className="club-detail-hero">
      <div className="club-detail-photo"><Image fill priority sizes="100vw" src="https://images.unsplash.com/photo-1542751371-adc38448a05e?auto=format&fit=crop&w=1800&q=90" alt={`${club.name} gaming floor`} /><span className="photo-caption"><span className="live-dot" /> CLUB / {club.city.toUpperCase()}</span><span className="photo-index">CR—{club.id.slice(0, 4).toUpperCase()}</span></div>
      <div className="club-detail-title"><div><div className="eyebrow"><MapPin size={13} /> {club.address} · {club.city}</div><h1>{club.name}</h1><p>{club.description}</p></div><div className="club-rating"><span>★</span>{Number(club.rating).toFixed(1)}<small>Club rating</small></div></div>
      <div className="club-facts"><span><ShieldCheck size={15} /> {availableComputers.length} PCs listed available</span><span><MonitorCog size={15} /> {club.computers.length} gaming stations</span><span><Clock3 size={15} /> Open daily</span><span>{club.phone}</span></div>
    </section>

    {club.price_menu?.tiers?.length > 0 && <ClubPriceMenuView menu={club.price_menu} />}

    {membershipPlansQuery.data && membershipPlansQuery.data.length > 0 && <section className="membership-offers"><div className="membership-offers-heading"><div><div className="eyebrow">HOUR PACKS</div><h2>More time, one purchase.</h2></div><span>Valid at this club</span></div><div className="membership-offer-grid">{membershipPlansQuery.data.map((plan) => <article className="membership-offer" key={plan.id}><div><strong>{plan.name}</strong><span>{plan.hours} hours · {plan.validity_days} days</span></div><p>{plan.description || "Prepaid gaming hours for this club."}</p><div className="membership-offer-buy"><strong>{Number(plan.price).toLocaleString("ru-RU")} KZT</strong><button type="button" disabled={!signedIn || membershipPurchaseMutation.isPending} onClick={() => membershipPurchaseMutation.mutate(plan)}>{signedIn ? "Buy hours" : "Sign in to buy"}</button></div></article>)}</div>{membershipPurchaseMutation.isError && <p className="form-error" role="alert">{membershipPurchaseMutation.error.message}</p>}</section>}

    {club.computers.length > 0 ? <section className="club-workspace">
      <div className="hardware-column"><div className="workspace-heading"><div><div className="eyebrow">CHOOSE YOUR STATION</div><h2>Find your rig.</h2></div><span>{availableComputers.length} available</span></div>
        <div className="computer-list">{club.computers.map((computer) => <ComputerRow key={computer.id} computer={computer} selected={computer.id === computerId} onSelect={() => setComputerId(computer.id)} />)}</div>
        <div className="tariff-list"><div className="eyebrow">HOURLY TARIFFS</div>{club.tariffs.map((tariff) => <div className="tariff-row" key={tariff.id}><span>{tariff.name}</span><span>{tariff.start_time.slice(0, 5)}–{tariff.end_time.slice(0, 5)}</span><strong>{Number(tariff.price_per_hour).toLocaleString("en-US")} KZT / HR</strong></div>)}</div>
      </div>

      <aside className="booking-panel"><div className="eyebrow">MAKE IT A SESSION <span>01 / 03</span></div><h2>Book a station.</h2><p className="booking-intro">Choose a time and we’ll calculate the exact price from the club’s tariffs. Paid bookings are refundable when cancelled at least {club.refund_cutoff_hours} hours before start.</p>
        <label className="booking-label">DATE · {club.timezone}<div className="input-wrap"><CalendarDays size={16} /><input type="date" min={todayAtClub} value={sessionDate} onChange={(event) => setSessionDate(event.target.value)} /></div></label>
        <div className="time-grid"><label className="booking-label">START<div className="input-wrap"><Clock3 size={15} /><input type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} /></div></label><label className="booking-label">END<div className="input-wrap"><Clock3 size={15} /><input type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} /></div></label></div>
        <label className="booking-label">COMPUTER<div className="selected-computer">{selectedComputer ? <><span>{selectedComputer.name}</span><small>{selectedComputer.gpu}</small></> : <span>Select a computer from the list</span>}</div></label>
        <label className="booking-label">PROMO CODE<input className="promo-input" value={promoCode} disabled={useMembership} onChange={(event) => setPromoCode(event.target.value.toUpperCase())} maxLength={32} autoComplete="off" placeholder="Optional code" /></label>
        {signedIn && hasMembershipHours && <label className="membership-checkbox"><input type="checkbox" checked={useMembership} onChange={(event) => { setUseMembership(event.target.checked); if (event.target.checked) setPromoCode(""); }} />Use package hours for this session</label>}
        {selectedComputer && <div className="staff-availability"><div className="eyebrow">RESERVED · {sessionDate || "CHOOSE DATE"}</div>
          {!sessionDate && <p>Choose a date to see reservations.</p>}
          {sessionDate && !dayRange && <p className="form-error">This date cannot be shown in the club time zone.</p>}
          {dayRange && availabilityQuery.isPending && <p>Loading reservations...</p>}
          {availabilityQuery.isError && <p className="form-error">{availabilityQuery.error.message}</p>}
          {availabilityQuery.isSuccess && busy.length === 0 && <p>No reservations on this date.</p>}
          {busy.map((slot, index) => <div className="staff-busy-slot" key={`${slot.start_time}-${index}`}><span>{new Date(slot.start_time).toLocaleTimeString("en-US", { timeZone: club.timezone, hour: "2-digit", minute: "2-digit" })}–{new Date(slot.end_time).toLocaleTimeString("en-US", { timeZone: club.timezone, hour: "2-digit", minute: "2-digit" })}</span><strong>Reserved</strong></div>)}
        </div>}
        {quoteQuery.data?.promo_code && Number(quoteQuery.data.discount_amount) > 0 && <div className="quote-row promo-discount"><span>Promo {quoteQuery.data.promo_code} · saved</span><strong>−{Number(quoteQuery.data.discount_amount).toLocaleString("en-US")} {quoteQuery.data.currency}</strong></div>}
        {quoteQuery.data && quoteQuery.data.membership_minutes > 0 && <div className="quote-row promo-discount"><span>Membership hours used</span><strong>{quoteQuery.data.membership_minutes / 60} hr</strong></div>}
        <div className="quote-row"><span>Estimated total</span><strong>{quoteQuery.isFetching ? "Calculating..." : quoteQuery.data ? `${Number(quoteQuery.data.total_price).toLocaleString("en-US")} ${quoteQuery.data.currency}` : "— KZT"}</strong></div>
        {selection.error && <p className="form-error" role="alert">{selection.error}</p>}
        {hasConflict && <p className="form-error" role="alert">This station is reserved during the selected time.</p>}
        {noComputersFree && <div className="waitlist-action"><p>Every bookable computer is reserved for this time.</p>{waitlistMutation.isError && <p className="form-error" role="alert">{waitlistMutation.error.message}</p>}{waitlistMutation.isSuccess ? <p className="role-success" role="status">You’re on the waitlist. We’ll alert you if a matching slot opens.</p> : <button type="button" className="waitlist-button" disabled={!signedIn || waitlistMutation.isPending} onClick={() => waitlistMutation.mutate()}>{waitlistMutation.isPending ? "Joining..." : signedIn ? "Join waitlist" : "Sign in to join the waitlist"}</button>}</div>}
        {quoteQuery.isError && <p className="form-error" role="alert">{quoteQuery.error.message}</p>}
        {bookingMutation.isError && <p className="form-error" role="alert">{bookingMutation.error.message}</p>}
        {!interval && <p className="form-hint">Choose a future date and a valid same-day time range.</p>}
        <button className="confirm-booking" type="button" disabled={!computerId || !interval || hasConflict || quoteQuery.isError || !quoteQuery.data || bookingMutation.isPending} onClick={() => bookingMutation.mutate()}>{bookingMutation.isPending ? "Confirming..." : signedIn ? "Confirm booking" : "Sign in to book"}<ArrowRight size={16} /></button>
        {!signedIn && <p className="auth-hint">You’ll need an account to confirm your booking. <Link href="/login">Sign in</Link></p>}
      </aside>
    </section> : <section className="bro-empty-hardware"><MonitorCog size={24} /><div><strong>Список компьютеров скоро появится</strong><span>Свяжитесь с клубом, чтобы уточнить свободные места.</span></div></section>}

    <section className="club-reviews">
      <div className="reviews-heading"><div><div className="eyebrow">PLAYER FEEDBACK</div><h2>Reviews from completed visits.</h2></div><strong>★ {Number(club.rating).toFixed(1)} <small>club rating</small></strong></div>
      {reviewsQuery.isPending && <p className="reviews-state">Loading reviews...</p>}
      {reviewsQuery.isError && <p className="reviews-state form-error">{reviewsQuery.error.message}</p>}
      {reviewsQuery.isSuccess && reviewsQuery.data.length === 0 && <p className="reviews-state">No reviews yet. Be the first to share feedback after a session.</p>}
      {reviewsQuery.data && reviewsQuery.data.length > 0 && <div className="reviews-grid">{reviewsQuery.data.map((review) => <article className="review-card" key={review.id}>
        <div className="review-card-top"><span>VERIFIED VISIT · {review.computer_name}</span><time>{new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium" }).format(new Date(review.created_at))}</time></div>
        <div className="review-score"><span>Клуб</span><strong>{"★".repeat(review.club_rating)}{"☆".repeat(5 - review.club_rating)}</strong></div>
        <div className="review-score"><span>Компьютер</span><strong>{"★".repeat(review.computer_rating)}{"☆".repeat(5 - review.computer_rating)}</strong></div>
        {review.comment && <p>{review.comment}</p>}
      </article>)}</div>}
    </section>
  </main>;
}
