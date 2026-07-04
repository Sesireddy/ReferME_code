import React, { useEffect, useState } from "react";
import { View, ActivityIndicator } from "react-native";
import { Tabs, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { colors } from "@/src/theme/tokens";
import { getToken, getUser } from "@/src/lib/api";

export default function AdminLayout() {
  const router = useRouter();
  const [authed, setAuthed] = useState<"checking" | "yes" | "no">("checking");

  useEffect(() => {
    (async () => {
      const token = await getToken();
      const user = await getUser();
      if (!token || !user || user.role !== "admin") {
        setAuthed("no");
        router.replace("/welcome");
        return;
      }
      setAuthed("yes");
    })();
  }, [router]);

  if (authed !== "yes") {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg }}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

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
      <Tabs.Screen name="audit-logs" options={{ href: null }} />
      <Tabs.Screen name="payouts" options={{ href: null }} />
      <Tabs.Screen name="disputes" options={{ href: null }} />
      {/* Admin Walk-in & Direct Jobs — hidden from tab bar, reached from admin dashboard/jobs */}
      <Tabs.Screen name="post-job" options={{ href: null }} />
      <Tabs.Screen name="my-posted-jobs" options={{ href: null }} />
    </Tabs>
  );
}
