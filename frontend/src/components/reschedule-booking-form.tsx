"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarDays, Clock3, MonitorCog } from "lucide-react";
import { authenticatedRequest, getClub } from "@/lib/api";
import { clubDate, clubLocalToIso } from "@/lib/club-time";
import type { Booking } from "@/types/api";

function localParts(value: string, timeZone: string) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(value)).map((part) => [part.type, part.value]));
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour}:${parts.minute}`,
  };
}

export function RescheduleBookingForm({ booking, accessToken, onSaved }: {
  booking: Booking;
  accessToken: string;
  onSaved: (booking: Booking) => void;
}) {
  const clubQuery = useQuery({ queryKey: ["club", booking.club_id], queryFn: () => getClub(booking.club_id) });
  const club = clubQuery.data;
  const [date, setDate] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [computerId, setComputerId] = useState(booking.computer_id);
  const [today] = useState(() => new Date());

  useEffect(() => {
    if (!club) return;
    setDate(localParts(booking.start_time, club.timezone).date);
    setStartTime(localParts(booking.start_time, club.timezone).time);
    setEndTime(localParts(booking.end_time, club.timezone).time);
  }, [booking, club]);

  const mutation = useMutation({
    mutationFn: () => {
      if (!club || !date || !startTime || !endTime || startTime >= endTime) {
        throw new Error("Choose a valid date and time interval.");
      }
      return authenticatedRequest<Booking>(`/bookings/${booking.id}/reschedule`, accessToken, "PATCH", {
        computer_id: computerId,
        start_time: clubLocalToIso(date, startTime, club.timezone),
        end_time: clubLocalToIso(date, endTime, club.timezone),
      });
    },
    onSuccess: onSaved,
  });

  const computers = club?.computers.filter((computer) => computer.is_active && !["DISABLED", "MAINTENANCE"].includes(computer.status)) ?? [];
  const validInterval = Boolean(date && startTime && endTime && startTime < endTime);

  return <section className="reschedule-panel">
    <div className="eyebrow">BOOKING OPTIONS</div>
    <h2>Change your reservation.</h2>
    <p>Choose a new time or another computer at {club?.name ?? "this club"}. The price will be recalculated using the club’s current tariffs.</p>
    {clubQuery.isError && <p className="form-error" role="alert">{clubQuery.error.message}</p>}
    <label className="booking-label">DATE · {club?.timezone ?? "CLUB TIME"}<span className="input-wrap"><CalendarDays size={15} /><input type="date" min={club ? clubDate(today, club.timezone) : undefined} value={date} onChange={(event) => setDate(event.target.value)} disabled={!club} /></span></label>
    <div className="time-grid">
      <label className="booking-label">START<span className="input-wrap"><Clock3 size={15} /><input type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} disabled={!club} /></span></label>
      <label className="booking-label">END<span className="input-wrap"><Clock3 size={15} /><input type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} disabled={!club} /></span></label>
    </div>
    <label className="booking-label">COMPUTER<span className="input-wrap"><MonitorCog size={15} /><select value={computerId} onChange={(event) => setComputerId(event.target.value)} disabled={!club}>
      {computers.map((computer) => <option key={computer.id} value={computer.id}>{computer.name} · {computer.gpu}</option>)}
    </select></span></label>
    {mutation.isError && <p className="form-error" role="alert">{mutation.error.message}</p>}
    {mutation.isSuccess && <p className="role-success" role="status">Reservation updated. New total: {Number(mutation.data.total_price).toLocaleString("ru-RU")} KZT.</p>}
    <button className="reschedule-submit" type="button" disabled={!club || !validInterval || !computerId || mutation.isPending || computers.length === 0} onClick={() => mutation.mutate()}>
      {mutation.isPending ? "Updating..." : "Save changes"}
    </button>
  </section>;
}
