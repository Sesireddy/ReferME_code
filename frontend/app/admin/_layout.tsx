import React, { useEffect, useState } from "react";
import { View, ActivityIndicator } from "react-native";
import { Stack, useRouter } from "expo-router";
import { colors } from "@/src/theme/tokens";
import { getToken, getUser } from "@/src/lib/api";

// Root Stack for the Admin area (with auth guard). Hidden pushed screens
// (audit-logs, payouts, disputes, post-job, my-posted-jobs) are stacked on top
// of the (tabs) group — back button performs a real one-step pop.
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
    <Stack screenOptions={{ headerShown: false, animation: "slide_from_right" }}>
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="audit-logs" />
      <Stack.Screen name="payouts" />
      <Stack.Screen name="disputes" />
      <Stack.Screen name="post-job" />
      <Stack.Screen name="my-posted-jobs" />
    </Stack>
  );
}
