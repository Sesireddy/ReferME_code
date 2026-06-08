import React from "react";
import { Redirect } from "expo-router";

/**
 * The old "Refer Candidate" pool screen has been retired.
 * Per spec, candidate referrals can ONLY happen from the pro's OWN posted jobs.
 * We use <Redirect /> (NOT useEffect+router.replace) so direct URL entry / refresh
 * also lands on My Posted Jobs without race conditions.
 */
export default function ReferRedirect() {
  return <Redirect href="/professional/my-jobs" />;
}
