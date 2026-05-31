import React, { useEffect } from "react";
import { View, StyleSheet, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Txt } from "@/src/components/Txt";
import { getToken, getUser, api, setSession } from "@/src/lib/api";
import { colors } from "@/src/theme/tokens";

export default function Index() {
  const router = useRouter();

  useEffect(() => {
    (async () => {
      try {
        const token = await getToken();
        if (!token) {
          router.replace("/welcome");
          return;
        }
        // Try to refresh user data
        try {
          const me = await api<{ user: any }>("/auth/me");
          await setSession(token, me.user);
          routeByRole(me.user.role, router);
        } catch {
          router.replace("/welcome");
        }
      } catch {
        router.replace("/welcome");
      }
    })();
  }, [router]);

  return (
    <LinearGradient colors={["#FFE8E9", "#FDFBF7", "#F0FFD0"]} style={styles.c} testID="splash-screen">
      <View style={styles.center}>
        <Txt variant="h1" style={{ color: colors.primary, fontSize: 48 }}>ReferME</Txt>
        <Txt variant="muted" style={{ marginTop: 8 }}>Mock interviews · referrals · payouts</Txt>
        <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
      </View>
    </LinearGradient>
  );
}

export function routeByRole(role: string, router: any) {
  if (role === "student") router.replace("/student/dashboard");
  else if (role === "professional") router.replace("/professional/dashboard");
  else if (role === "employer") router.replace("/employer/dashboard");
  else if (role === "admin") router.replace("/admin/dashboard");
  else router.replace("/welcome");
}

const styles = StyleSheet.create({
  c: { flex: 1 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
});
