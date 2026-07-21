import React from "react";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors } from "@/src/theme/tokens";
import { TAB_ICON_MAP, TAB_INACTIVE } from "@/src/theme/tabIcons";

// Bottom Tabs for the Admin area. Only tab-visible screens live here.
// Hidden pushed screens (audit-logs, payouts, disputes, post-job, my-posted-jobs)
// live in the PARENT `admin/` folder inside the parent Stack — so `router.back()`
// performs a real one-step pop from those screens.
//
// Iter 73 — Nav icons render in a distinct pastel hue when active (per-route
// palette from `tabIcons.ts`) and muted slate-400 when inactive.
// Iter 74 — Reserve extra bottom padding (via safe-area insets) so the tab
// bar is fully clickable on Android 3-button navigation.
export default function AdminTabsLayout() {
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
        tabBarLabelStyle: { fontSize: 10, fontWeight: "600" },
      }}
    >
      <Tabs.Screen name="dashboard"    options={{ title: "Dashboard",  tabBarIcon: iconFor("dashboard") }} />
      <Tabs.Screen name="users"        options={{ title: "Users",      tabBarIcon: iconFor("users") }} />
      <Tabs.Screen name="jobs"         options={{ title: "Jobs",       tabBarIcon: iconFor("jobs") }} />
      <Tabs.Screen name="interviews"   options={{ title: "Interviews", tabBarIcon: iconFor("interviews") }} />
      <Tabs.Screen name="transactions" options={{ title: "Credits",    tabBarIcon: iconFor("transactions") }} />
      <Tabs.Screen name="redemptions"  options={{ title: "Approvals",  tabBarIcon: iconFor("redemptions") }} />
    </Tabs>
  );
}
