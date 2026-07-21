import React from "react";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
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
// Iter 74 — Reserve extra bottom padding (via safe-area insets) so the tab bar
// is fully clickable on Android devices that still use 3-button navigation.
// `edgeToEdgeEnabled` in app.json draws under the system nav, so we must
// account for it manually.
export default function StudentTabsLayout() {
  const insets = useSafeAreaInsets();
  const bottomPad = Math.max(insets.bottom, 8);
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
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          height: 60 + bottomPad,
          paddingBottom: bottomPad,
          paddingTop: 6,
        },
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
