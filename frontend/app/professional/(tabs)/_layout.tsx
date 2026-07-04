import React from "react";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { colors } from "@/src/theme/tokens";

// Tabs for the Professional area. Only tab-visible screens live here.
// Hidden pushed screens (Wallet, Redeem, Refer, Payout, My Mock Interviews, My Leaderboard)
// live in the PARENT `professional/` folder and are rendered inside the parent Stack —
// so `router.push()` truly pushes them on top of the tabs and `router.back()` pops back
// to the previously focused tab.
export default function ProTabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: "#7C3AED",
        tabBarInactiveTintColor: colors.textSecondary,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border, height: 64, paddingBottom: 8, paddingTop: 6 },
        tabBarLabelStyle: { fontSize: 10, fontWeight: "600" },
      }}
    >
      <Tabs.Screen name="dashboard" options={{ title: "Home", tabBarIcon: ({ color, size }) => <Ionicons name="home" size={size} color={color} /> }} />
      <Tabs.Screen name="slots" options={{ title: "Interviews", tabBarIcon: ({ color, size }) => <Ionicons name="videocam" size={size} color={color} /> }} />
      <Tabs.Screen name="my-jobs" options={{ title: "My Jobs", tabBarIcon: ({ color, size }) => <Ionicons name="folder-open" size={size} color={color} /> }} />
      <Tabs.Screen name="post-job" options={{ title: "Post a Job", tabBarIcon: ({ color, size }) => <Ionicons name="add-circle" size={size} color={color} /> }} />
      <Tabs.Screen name="profile" options={{ title: "Profile", tabBarIcon: ({ color, size }) => <Ionicons name="person" size={size} color={color} /> }} />
    </Tabs>
  );
}
