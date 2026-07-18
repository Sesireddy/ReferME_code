import { Router } from "expo-router";
import { webSafeAlert } from "@/src/lib/webSafeAlert";

/**
 * Iter 69 — Standardized Join Meeting handler.
 *
 * If the interview's `join_enabled` flag from the backend is `true`, navigate
 * to the in-app video screen (`/video/{slotId}`). Otherwise show the standard
 * "Join Meeting Not Available" popup so both Job Seekers and Working
 * Professionals see the same UX.
 */
export function tryJoinMeeting(booking: { id: string; join_enabled?: boolean }, router: Router) {
  if (booking?.join_enabled) {
    router.push(`/video/${booking.id}`);
    return;
  }
  webSafeAlert(
    "Join Meeting Not Available",
    "You can join the meeting only 10 minutes before the scheduled interview time. Please try again later."
  );
}
