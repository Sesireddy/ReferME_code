import React from "react";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { colors } from "@/src/theme/tokens";

// Bottom Tabs for the Admin area. Only tab-visible screens live here.
// Hidden pushed screens (audit-logs, payouts, disputes, post-job, my-posted-jobs)
// live in the PARENT `admin/` folder inside the parent Stack — so `router.back()`
// performs a real one-step pop from those screens.
export default function AdminTabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textSecondary,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border, height: 64, paddingBottom: 8, paddingTop: 6 },
        tabBarLabelStyle: { fontSize: 10, fontWeight: "600" },
      }}
    >
      <Tabs.Screen name="dashboard" options={{ title: "Dashboard", tabBarIcon: ({ color, size }) => <Ionicons name="stats-chart" size={size} color={color} /> }} />
      <Tabs.Screen name="users" options={{ title: "Users", tabBarIcon: ({ color, size }) => <Ionicons name="people" size={size} color={color} /> }} />
      <Tabs.Screen name="jobs" options={{ title: "Jobs", tabBarIcon: ({ color, size }) => <Ionicons name="briefcase" size={size} color={color} /> }} />
      <Tabs.Screen name="interviews" options={{ title: "Interviews", tabBarIcon: ({ color, size }) => <Ionicons name="videocam" size={size} color={color} /> }} />
      <Tabs.Screen name="transactions" options={{ title: "Credits", tabBarIcon: ({ color, size }) => <Ionicons name="card" size={size} color={color} /> }} />
      <Tabs.Screen name="redemptions" options={{ title: "Approvals", tabBarIcon: ({ color, size }) => <Ionicons name="checkmark-done-circle" size={size} color={color} /> }} />
    </Tabs>
  );
}
