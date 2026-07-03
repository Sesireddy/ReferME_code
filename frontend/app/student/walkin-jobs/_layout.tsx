import React from "react";
import { Stack } from "expo-router";

// Nested Stack so router.push()/router.back() between the list and details
// stays contained within walk-in jobs (instead of switching tabs at the root).
export default function WalkinJobsLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="[id]" />
    </Stack>
  );
}
