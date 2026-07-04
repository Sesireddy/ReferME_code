import React from "react";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { colors } from "@/src/theme/tokens";

// Bottom Tabs for the Student area. Only tab-visible screens live here.
// Hidden pushed screens (Wallet, Applications, Walk-in Jobs, etc.) live in the PARENT
// `student/` folder and are rendered inside the parent Stack — so `router.push()`
// truly pushes them on top of the tabs and `router.back()` pops back to the caller.
export default function StudentTabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textSecondary,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border, height: 64, paddingBottom: 8, paddingTop: 6 },
        tabBarLabelStyle: { fontSize: 9, fontWeight: "600" },
        tabBarItemStyle: { paddingHorizontal: 0 },
      }}
    >
      <Tabs.Screen name="dashboard" options={{ title: "Home", tabBarIcon: ({ color, size }) => <Ionicons name="home" size={size} color={color} /> }} />
      <Tabs.Screen name="jobs" options={{ title: "Jobs", tabBarIcon: ({ color, size }) => <Ionicons name="briefcase" size={size} color={color} /> }} />
      <Tabs.Screen name="mock-interviews" options={{ title: "Interviews", tabBarIcon: ({ color, size }) => <Ionicons name="videocam" size={size} color={color} /> }} />
      <Tabs.Screen name="leaderboard" options={{ title: "LeadBoard", tabBarIcon: ({ color, size }) => <Ionicons name="trophy" size={size} color={color} /> }} />
      <Tabs.Screen name="profile" options={{ title: "Profile", tabBarIcon: ({ color, size }) => <Ionicons name="person" size={size} color={color} /> }} />
    </Tabs>
  );
}
