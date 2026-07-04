import React from "react";
import { Stack } from "expo-router";

// Root Stack for the Professional area.
//
// Structure:
//   professional/
//     _layout.tsx         <- THIS Stack (root)
//     (tabs)/             <- Bottom-tab group (Home, Interviews, My Jobs, Post a Job, Profile)
//     wallet.tsx          <- Pushed on top of tabs — one-step-back returns to the caller
//     redeem.tsx          <- ditto
//     refer.tsx           <- ditto
//     payout.tsx          <- ditto
//     my-mock-interviews.tsx
//     my-leaderboard.tsx
//
// Because Wallet/Redeem/etc. are NOT tab entries anymore, `router.push()` truly stacks
// them and `router.back()` performs a real pop — exactly one step back to the caller.
export default function ProfessionalLayout() {
  return (
    <Stack screenOptions={{ headerShown: false, animation: "slide_from_right" }}>
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="wallet" />
      <Stack.Screen name="redeem" />
      <Stack.Screen name="refer" />
      <Stack.Screen name="payout" />
      <Stack.Screen name="my-mock-interviews" />
      <Stack.Screen name="my-leaderboard" />
    </Stack>
  );
}
