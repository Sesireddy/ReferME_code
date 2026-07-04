import React from "react";
import { Stack } from "expo-router";

// Root Stack for the Student area. Hidden pushed screens (Wallet, Applications,
// Walk-in Jobs, etc.) are declared here so `router.push()` truly pushes them on top
// of the tabs — `router.back()` then performs a real one-step pop back to the caller.
export default function StudentLayout() {
  return (
    <Stack screenOptions={{ headerShown: false, animation: "slide_from_right" }}>
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="wallet" />
      <Stack.Screen name="applications" />
      <Stack.Screen name="my-applications" />
      <Stack.Screen name="my-mock-interviews" />
      <Stack.Screen name="my-leaderboard" />
      <Stack.Screen name="refer" />
      <Stack.Screen name="walkin-jobs" />
    </Stack>
  );
}
