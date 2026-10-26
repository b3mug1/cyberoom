"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { authenticatedRequest } from "@/lib/api";
import type { Booking, Review } from "@/types/api";

export function BookingReviewForm({ booking, accessToken, onSaved }: {
  booking: Booking;
  accessToken: string;
  onSaved: (review: Review) => void;
}) {
  const [clubRating, setClubRating] = useState(5);
  const [computerRating, setComputerRating] = useState(5);
  const [comment, setComment] = useState("");
  const mutation = useMutation({
    mutationFn: () => authenticatedRequest<Review>(`/bookings/${booking.id}/review`, accessToken, "POST", {
      club_rating: clubRating,
      computer_rating: computerRating,
      comment,
    }),
    onSuccess: onSaved,
  });

  return <section className="review-panel">
    <div className="eyebrow">AFTER YOUR SESSION</div>
    <h2>{booking.review ? "Your review." : "How was the session?"}</h2>
    {booking.review ? <div className="saved-review">
      <p><strong>Club</strong><span>{"★".repeat(booking.review.club_rating)}{"☆".repeat(5 - booking.review.club_rating)}</span></p>
      <p><strong>Computer</strong><span>{"★".repeat(booking.review.computer_rating)}{"☆".repeat(5 - booking.review.computer_rating)}</span></p>
      {booking.review.comment && <blockquote>{booking.review.comment}</blockquote>}
    </div> : <>
      <p>Share a rating for the club and this computer after your completed visit.</p>
      <div className="review-fields">
        <label>Club rating<select value={clubRating} onChange={(event) => setClubRating(Number(event.target.value))}>{[5, 4, 3, 2, 1].map((value) => <option key={value} value={value}>{value} / 5</option>)}</select></label>
        <label>Computer rating<select value={computerRating} onChange={(event) => setComputerRating(Number(event.target.value))}>{[5, 4, 3, 2, 1].map((value) => <option key={value} value={value}>{value} / 5</option>)}</select></label>
        <label className="review-comment">Comment (optional)<textarea value={comment} maxLength={2000} onChange={(event) => setComment(event.target.value)} placeholder="What should other players know?" /></label>
      </div>
      {mutation.isError && <p className="form-error" role="alert">{mutation.error.message}</p>}
      <button className="reschedule-submit" type="button" disabled={mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? "Sending..." : "Send review"}</button>
    </>}
  </section>;
}
