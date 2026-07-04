import React from "react";
import { Stack } from "expo-router";

// Nested Stack so `router.push('/professional/my-jobs/[id]')` stacks the detail
// on top of the list — and `router.back()` from the detail pops back to the
// list (rather than jumping to the previously focused parent tab).
export default function ProMyJobsLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="[id]" />
    </Stack>
  );
}
