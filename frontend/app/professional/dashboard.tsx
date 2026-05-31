import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function ProDashboard() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [rank, setRank] = useState<number | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const me = await api<{ user: any }>("/auth/me");
      setUser(me.user);
      const lb = await api<any[]>("/leaderboard/professionals");
      setRank(lb.find((x) => x.is_me)?.rank ?? null);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={styles.header}>
        <View>
          <Txt variant="label">Hey,</Txt>
          <Txt variant="h2">{user?.name || (user?.email || "").split("@")[0]}</Txt>
        </View>
        <TouchableOpacity testID="notif-btn" onPress={() => router.push("/notifications")}>
          <View style={styles.iconBtn}><Ionicons name="notifications" size={22} color={colors.textPrimary} /></View>
        </TouchableOpacity>
      </View>

      <LinearGradient colors={["#7C3AED", "#A855F7"]} start={{x:0,y:0}} end={{x:1,y:1}} style={styles.hero}>
        <View>
          <Txt style={{ color: "#fff", opacity: 0.85 }} variant="label">Credits earned</Txt>
          <Txt style={{ color: "#fff", fontSize: 44, fontWeight: "800", marginTop: 4 }}>{user?.credits ?? 0}</Txt>
          <Txt style={{ color: "#fff", opacity: 0.9 }}>Redeem after 500 credits</Txt>
        </View>
      </LinearGradient>

      <View style={styles.row}>
        <Card style={styles.statBox}>
          <Txt variant="label" style={{ color: "#7C3AED" }}>Interviews</Txt>
          <Txt variant="h1" style={{ marginTop: 4 }}>{user?.interviews_conducted ?? 0}</Txt>
          <Txt variant="small" style={{ color: colors.textSecondary }}>conducted</Txt>
        </Card>
        <Card style={styles.statBox}>
          <Txt variant="label" style={{ color: colors.primary }}>Referrals</Txt>
          <Txt variant="h1" style={{ marginTop: 4 }}>{user?.referrals_made ?? 0}</Txt>
          <Txt variant="small" style={{ color: colors.textSecondary }}>made</Txt>
        </Card>
      </View>

      <Card style={{ marginTop: 12 }}>
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          <View style={[styles.rankIcon, { backgroundColor: "#FFF4E0" }]}>
            <Ionicons name="trophy" size={28} color={colors.accent} />
          </View>
          <View style={{ flex: 1, marginLeft: 14 }}>
            <Txt variant="label">Leaderboard</Txt>
            <Txt variant="h3">{rank ? `Rank #${rank}` : "Not ranked yet"}</Txt>
          </View>
        </View>
      </Card>

      <View style={styles.row}>
        <TouchableOpacity testID="cta-conduct" style={{ flex: 1 }} onPress={() => router.push("/professional/slots")}>
          <Card style={{ borderColor: "#7C3AED", borderWidth: 2 }}>
            <Ionicons name="videocam" size={24} color="#7C3AED" />
            <Txt variant="h3" style={{ marginTop: 8 }}>Conduct Interview</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>+25 credits each</Txt>
          </Card>
        </TouchableOpacity>
        <TouchableOpacity testID="cta-refer" style={{ flex: 1 }} onPress={() => router.push("/professional/refer")}>
          <Card style={{ borderColor: colors.secondary, borderWidth: 2 }}>
            <Ionicons name="share-social" size={24} color={colors.textPrimary} />
            <Txt variant="h3" style={{ marginTop: 8 }}>Refer Candidate</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>+500 if hired</Txt>
          </Card>
        </TouchableOpacity>
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 16 },
  iconBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  hero: { padding: 20, borderRadius: radius.xxl },
  row: { flexDirection: "row", gap: 12, marginTop: 12 },
  statBox: { flex: 1 },
  rankIcon: { width: 56, height: 56, borderRadius: 18, alignItems: "center", justifyContent: "center" },
});
