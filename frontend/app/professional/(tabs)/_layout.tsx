import React from "react";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors } from "@/src/theme/tokens";
import { TAB_ICON_MAP, TAB_INACTIVE } from "@/src/theme/tabIcons";

// Tabs for the Professional area. Only tab-visible screens live here.
// Hidden pushed screens (Wallet, Redeem, Refer, Payout, My Mock Interviews, My Leaderboard)
// live in the PARENT `professional/` folder and are rendered inside the parent Stack —
// so `router.push()` truly pushes them on top of the tabs and `router.back()` pops back
// to the previously focused tab.
//
// Iter 73 — Nav icons render in a distinct pastel hue when active (per-route
// palette from `tabIcons.ts`) and muted slate-400 when inactive.
// Iter 74 — Reserve extra bottom padding (via safe-area insets) so the tab
// bar is fully clickable on Android 3-button navigation.
export default function ProTabsLayout() {
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
      <Tabs.Screen name="dashboard" options={{ title: "Home",       tabBarIcon: iconFor("dashboard") }} />
      <Tabs.Screen name="slots"     options={{ title: "Interviews", tabBarIcon: iconFor("slots") }} />
      <Tabs.Screen name="my-jobs"   options={{ title: "My Jobs",    tabBarIcon: iconFor("my-jobs") }} />
      <Tabs.Screen name="post-job"  options={{ title: "Post a Job", tabBarIcon: iconFor("post-job") }} />
      <Tabs.Screen name="profile"   options={{ title: "Profile",    tabBarIcon: iconFor("profile") }} />
    </Tabs>
  );
}
