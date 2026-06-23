import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { SafeAreaView } from "react-native-safe-area-context";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

type Stats = {
  rank?: number | null;
  interviews_conducted: number;
  jobs_posted: number;
  wps: number;
  rating?: number;
  ratings_count?: number;
  successful_referrals?: number;
  total_pros?: number;
};

export default function ProMyLeaderboard() {
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await api<Stats>("/leaderboard/professional/me/stats");
      setStats(r);
    } catch {}
    setRefreshing(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const wps = Math.round(Number(stats?.wps ?? 0));
  const interviews = Number(stats?.interviews_conducted ?? 0);
  const jobs = Number(stats?.jobs_posted ?? 0);
  const rank = stats?.rank;
  const rating = Number(stats?.rating ?? 0);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={["top"]}>
      <View style={styles.header}>
        <TouchableOpacity testID="back-btn" onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="chevron-back" size={28} color={colors.textPrimary} />
        </TouchableOpacity>
        <Txt variant="h3">LeaderBoard</Txt>
        <View style={{ width: 28 }} />
      </View>

      <Screen refreshing={refreshing} onRefresh={load}>
        <LinearGradient colors={["#7C3AED", "#A855F7"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.hero}>
          <View style={{ flex: 1 }}>
            <Txt style={styles.heroLabel}>YOUR RANK</Txt>
            <Txt style={styles.heroValue}>#{rank ?? "—"}</Txt>
            <Txt style={styles.heroSub}>Working Professional Score</Txt>
          </View>
          <View style={styles.wpsPill}>
            <Txt style={styles.wpsValue}>{wps}</Txt>
            <Txt style={styles.wpsMax}>/100</Txt>
          </View>
        </LinearGradient>

        <View style={styles.grid}>
          <StatCard icon="videocam" iconColor="#7C3AED" bg="#F5F3FF" label="Interviews Conducted" value={`${interviews}`} />
          <StatCard icon="briefcase" iconColor="#2563EB" bg="#EFF6FF" label="Jobs Posted" value={`${jobs}`} />
          <StatCard icon="star" iconColor="#F59E0B" bg="#FFFBEB" label="Average Rating" value={rating > 0 ? `★ ${rating.toFixed(1)}/10` : "—"} />
          <StatCard icon="trophy" iconColor="#EF4444" bg="#FEF2F2" label="WPS" value={`${wps}/100`} />
        </View>

        <Card style={{ marginTop: 16 }}>
          <Txt variant="h3" style={{ marginBottom: 8 }}>How WPS is calculated</Txt>
          <Bullet>
            <Txt style={{ fontWeight: "800" }}>60% Interview Activity</Txt> — based on the total mock interviews you have conducted.
          </Bullet>
          <Bullet>
            <Txt style={{ fontWeight: "800" }}>40% Job Posting Activity</Txt> — based on the total jobs you have posted.
          </Bullet>
          <Bullet>
            Rank rises automatically as you conduct more interviews and post more roles.
          </Bullet>
        </Card>

        <TouchableOpacity testID="open-board" onPress={load} style={styles.openLb}>
          <Ionicons name="refresh" size={16} color="#7C3AED" />
          <Txt style={styles.openLbText}>Refresh ranking</Txt>
        </TouchableOpacity>
      </Screen>
    </SafeAreaView>
  );
}

function StatCard({ icon, iconColor, bg, label, value }: { icon: any; iconColor: string; bg: string; label: string; value: string }) {
  return (
    <View style={[styles.statCard, { backgroundColor: bg }]}>
      <View style={[styles.statIcon, { backgroundColor: iconColor + "22" }]}>
        <Ionicons name={icon} size={18} color={iconColor} />
      </View>
      <View style={{ flex: 1 }}>
        <Txt style={{ color: iconColor, fontWeight: "700", fontSize: 12 }} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>{label}</Txt>
        <Txt style={{ fontWeight: "800", fontSize: 18, marginTop: 2 }} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>{value}</Txt>
      </View>
    </View>
  );
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <View style={{ flexDirection: "row", marginTop: 4 }}>
      <Txt style={{ color: "#7C3AED", marginRight: 6 }}>•</Txt>
      <Txt style={{ flex: 1, color: colors.textPrimary, lineHeight: 20 }}>{children}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border },
  hero: { flexDirection: "row", alignItems: "center", padding: 18, borderRadius: radius.xxl, marginBottom: 16, minHeight: 130 },
  heroLabel: { color: "rgba(255,255,255,0.95)", fontWeight: "700", letterSpacing: 0.5, fontSize: 12 },
  heroValue: { color: "#fff", fontSize: 44, fontWeight: "900", lineHeight: 50, marginTop: 4 },
  heroSub: { color: "rgba(255,255,255,0.95)", marginTop: 4, fontSize: 12, fontWeight: "600" },
  wpsPill: { flexDirection: "row", alignItems: "baseline", backgroundColor: "#fff", paddingHorizontal: 16, paddingVertical: 8, borderRadius: 14 },
  wpsValue: { fontSize: 32, fontWeight: "900", color: "#1A1A2E" },
  wpsMax: { fontSize: 14, fontWeight: "700", color: colors.textSecondary, marginLeft: 4 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  statCard: { width: "48%", flexDirection: "row", alignItems: "center", padding: 12, borderRadius: radius.lg, gap: 10 },
  statIcon: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  openLb: { flexDirection: "row", alignItems: "center", justifyContent: "center", paddingVertical: 12, marginTop: 14, gap: 6, borderRadius: radius.lg, borderWidth: 1, borderColor: "#7C3AED", backgroundColor: "#7C3AED0F" },
  openLbText: { fontWeight: "700", color: "#7C3AED" },
});
