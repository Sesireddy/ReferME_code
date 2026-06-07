import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, Image, Alert } from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { colors, radius } from "@/src/theme/tokens";
import { api, getUser } from "@/src/lib/api";

const COIN = "https://static.prod-images.emergentagent.com/jobs/d2f455eb-160b-40ff-9a4e-1d583c1869b0/images/9e5ea04b28cbe7d19560f639172fa32c7ea2e010c38001356192231f7835193d.png";

export default function StudentDashboard() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [rank, setRank] = useState<number | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const me = await api<{ user: any }>("/auth/me");
      setUser(me.user);
      const lb = await api<any[]>("/leaderboard/students");
      const meRank = lb.find((s) => s.is_me);
      setRank(meRank?.rank ?? null);
    } catch (e: any) {
      // ignore
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={styles.header}>
        <View>
          <Txt variant="label">Hello,</Txt>
          <Txt variant="h2" testID="student-name">{user?.name || (user?.email || "").split("@")[0]}</Txt>
        </View>
        <TouchableOpacity testID="notif-btn" onPress={() => router.push("/notifications")}>
          <View style={styles.iconBtn}>
            <Ionicons name="notifications" size={22} color={colors.textPrimary} />
          </View>
        </TouchableOpacity>
      </View>

      <LinearGradient
        colors={["#FF5A5F", "#FFB347"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.walletCard}
      >
        <View style={{ flex: 1 }}>
          <Txt style={{ color: "#fff", opacity: 0.8 }} variant="label">Wallet balance</Txt>
          <Txt style={{ color: "#fff", fontSize: 40, fontWeight: "800", marginTop: 4 }} testID="student-credits">
            {user?.credits ?? 0}
          </Txt>
          <Txt style={{ color: "#fff", opacity: 0.9, marginTop: 2 }} variant="small">
            credits · {user?.free_uses_left ?? 0} free uses
          </Txt>
        </View>
        <Image source={{ uri: COIN }} style={{ width: 96, height: 96 }} />
      </LinearGradient>

      <View style={styles.actionRow}>
        <TouchableOpacity
          testID="cta-book-interview"
          style={{ flex: 1 }}
          onPress={() => router.push("/student/mock-interviews")}
        >
          <Card style={{ borderColor: colors.secondary, borderWidth: 2 }}>
            <View style={[styles.actionIcon, { backgroundColor: "#F5FFD0" }]}>
              <Ionicons name="videocam" size={24} color={colors.textPrimary} />
            </View>
            <Txt variant="h3" style={{ marginTop: 12 }}>Book Mock Interview</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>49 credits / free</Txt>
          </Card>
        </TouchableOpacity>
        <TouchableOpacity testID="cta-apply-job" style={{ flex: 1 }} onPress={() => router.push("/student/jobs")}>
          <Card style={{ borderColor: colors.primary, borderWidth: 2 }}>
            <View style={[styles.actionIcon, { backgroundColor: "#FFE4E5" }]}>
              <Ionicons name="paper-plane" size={22} color={colors.primary} />
            </View>
            <Txt variant="h3" style={{ marginTop: 12 }}>Apply for Referral</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>49 credits / free</Txt>
          </Card>
        </TouchableOpacity>
      </View>

      <Card style={{ marginTop: 16 }}>
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          <View style={[styles.rankIcon, { backgroundColor: "#FFF4E0" }]}>
            <Ionicons name="trophy" size={28} color={colors.accent} />
          </View>
          <View style={{ flex: 1, marginLeft: 14 }}>
            <Txt variant="label">Leaderboard</Txt>
            <Txt variant="h3" style={{ marginTop: 2 }}>
              {rank ? `Rank #${rank}` : "Not ranked yet"}
            </Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
              Attend interviews & boost resume score
            </Txt>
          </View>
          <TouchableOpacity onPress={() => router.push("/student/leaderboard")}>
            <Ionicons name="chevron-forward" size={22} color={colors.textSecondary} />
          </TouchableOpacity>
        </View>
      </Card>

      {!user?.profile_complete ? (
        <Card style={{ marginTop: 16, backgroundColor: "#FFF9E5", borderColor: "#FFD566", borderWidth: 1 }}>
          <Txt variant="h3">Complete your profile 🎯</Txt>
          <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>
            Profiles with resume + skills get 3x more referrals.
          </Txt>
          <Button testID="complete-profile" title="Set up now" onPress={() => router.push("/student/profile")} style={{ marginTop: 12 }} />
        </Card>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 16 },
  iconBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  walletCard: { borderRadius: radius.xxl, padding: 20, flexDirection: "row", alignItems: "center", marginBottom: 16 },
  actionRow: { flexDirection: "row", gap: 12 },
  actionIcon: { width: 44, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  rankIcon: { width: 56, height: 56, borderRadius: 18, alignItems: "center", justifyContent: "center" },
});
