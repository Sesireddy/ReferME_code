import React from "react";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { colors } from "@/src/theme/tokens";
import { TAB_ICON_MAP, TAB_INACTIVE } from "@/src/theme/tabIcons";

// Bottom Tabs for the Student area. Only tab-visible screens live here.
// Hidden pushed screens (Wallet, Applications, Walk-in Jobs, etc.) live in the PARENT
// `student/` folder and are rendered inside the parent Stack — so `router.push()`
// truly pushes them on top of the tabs and `router.back()` pops back to the caller.
//
// Iter 73 — Nav icons render in a distinct pastel hue when active (per-route
// palette from `tabIcons.ts`) and muted slate-400 when inactive, for a modern
// LinkedIn/Naukri feel while staying visually calm.
export default function StudentTabsLayout() {
  const iconFor = (route: keyof typeof TAB_ICON_MAP) => {
    const TabIcon = ({ focused, size }: { focused: boolean; size: number }) => {
      const cfg = TAB_ICON_MAP[route];
      return (
        <Ionicons
          name={cfg.name}
          size={size}
          color={focused ? cfg.activeColor : TAB_INACTIVE}
        />
      );
    };
    TabIcon.displayName = `TabIcon(${route})`;
    return TabIcon;
  };

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.textPrimary,
        tabBarInactiveTintColor: TAB_INACTIVE,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border, height: 64, paddingBottom: 8, paddingTop: 6 },
        tabBarLabelStyle: { fontSize: 9, fontWeight: "600" },
        tabBarItemStyle: { paddingHorizontal: 0 },
      }}
    >
      <Tabs.Screen name="dashboard"       options={{ title: "Home",       tabBarIcon: iconFor("dashboard") }} />
      <Tabs.Screen name="jobs"            options={{ title: "Jobs",       tabBarIcon: iconFor("jobs") }} />
      <Tabs.Screen name="mock-interviews" options={{ title: "Interviews", tabBarIcon: iconFor("mock-interviews") }} />
      <Tabs.Screen name="leaderboard"     options={{ title: "LeadBoard",  tabBarIcon: iconFor("leaderboard") }} />
      <Tabs.Screen name="profile"         options={{ title: "Profile",    tabBarIcon: iconFor("profile") }} />
    </Tabs>
  );
}
