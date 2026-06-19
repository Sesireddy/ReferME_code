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

type Ranks = {
  overall_rank?: number | null;
  category_rank?: number | null;
  skill_rank?: number | null;
  primary_skill?: string | null;
  category_label?: string | null;
};

export default function MyLeaderboardScore() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [profile, setProfile] = useState<any>({});
  const [ranks, setRanks] = useState<Ranks>({});
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const me = await api<{ user: any; profile: any }>("/auth/me");
      setUser(me.user);
      setProfile(me.profile || {});
      try {
        const r = await api<Ranks>("/leaderboard/student/me/ranks");
        setRanks(r || {});
      } catch {}
    } catch {}
    setRefreshing(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const tps = Math.round(Number(profile?.tps ?? 0));
  const resumeScore = Number(profile?.resume_score ?? 0);
  const interviews = Number(user?.interviews_attended ?? 0);
  const avgRating = Number(user?.student_rating ?? 0); // 0..10

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={["top"]}>
      <View style={styles.header}>
        <TouchableOpacity testID="back-btn" onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="chevron-back" size={28} color={colors.textPrimary} />
        </TouchableOpacity>
        <Txt variant="h3">My LeaderBoard Score</Txt>
        <View style={{ width: 28 }} />
      </View>

      <Screen refreshing={refreshing} onRefresh={load}>
        {/* Hero — Current rank + TPS */}
        <LinearGradient colors={["#FF5A5F", "#FFB347"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.hero}>
          <View style={{ flex: 1 }}>
            <Txt style={styles.heroLabel}>YOUR RANK</Txt>
            <View style={{ flexDirection: "row", alignItems: "baseline", marginTop: 4 }}>
              <Txt style={styles.heroValue}>#{ranks.overall_rank ?? "—"}</Txt>
            </View>
            <Txt style={styles.heroSub}>Talent Potential Score</Txt>
          </View>
          <View style={styles.tpsPill}>
            <Txt style={styles.tpsValue}>{tps}</Txt>
            <Txt style={styles.tpsMax}>/100</Txt>
          </View>
        </LinearGradient>

        {/* Stats grid */}
        <View style={styles.grid}>
          <StatCard icon="document-text" iconColor="#2563EB" bg="#EFF6FF" label="Resume Score" value={`${resumeScore}/100`} />
          <StatCard icon="videocam" iconColor="#7C3AED" bg="#F5F3FF" label="Interviews Attended" value={`${interviews}`} />
          <StatCard icon="star" iconColor="#F59E0B" bg="#FFFBEB" label="Average Rating" value={avgRating > 0 ? `★ ${avgRating.toFixed(1)}/10` : "—"} />
          <StatCard icon="trophy" iconColor="#EF4444" bg="#FEF2F2" label="TPS" value={`${tps}/100`} />
        </View>

        {/* Rank breakdown */}
        <Card style={{ marginTop: 16 }}>
          <Txt variant="h3" style={{ marginBottom: 8 }}>Ranking breakdown</Txt>
          <RankRow icon="podium" label="Overall Rank" value={ranks.overall_rank ?? "—"} hint="Across all Job Seekers" />
          <RankRow
            icon="ribbon"
            label="Category Rank"
            value={ranks.category_rank ?? "—"}
            hint={ranks.category_label ? `Among ${ranks.category_label}s` : "Among your category"}
          />
          <RankRow
            icon="briefcase"
            label="Skill Set Rank"
            value={ranks.skill_rank ?? "—"}
            hint={ranks.primary_skill ? `Among ${ranks.primary_skill} candidates` : "Among your primary skill"}
            last
          />
        </Card>

        <TouchableOpacity testID="open-lb" onPress={() => router.push("/student/leaderboard")} style={styles.openLb}>
          <Ionicons name="trophy" size={16} color={colors.primary} />
          <Txt style={styles.openLbText}>View full Leaderboard</Txt>
          <Ionicons name="chevron-forward" size={16} color={colors.primary} />
        </TouchableOpacity>

        <Txt variant="small" style={{ color: colors.textSecondary, textAlign: "center", marginTop: 12 }}>
          TPS = 60% Resume + 20% Interviews + 20% Avg Rating. Higher TPS = better rank.
        </Txt>
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
        <Txt style={{ color: iconColor, fontWeight: "700", fontSize: 12 }} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>
          {label}
        </Txt>
        <Txt style={{ fontWeight: "800", fontSize: 18, marginTop: 2 }} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>
          {value}
        </Txt>
      </View>
    </View>
  );
}

function RankRow({ icon, label, value, hint, last }: { icon: any; label: string; value: any; hint?: string; last?: boolean }) {
  return (
    <View style={[styles.rankRow, !last && styles.rankRowBorder]}>
      <View style={styles.rankIcon}>
        <Ionicons name={icon} size={18} color={colors.primary} />
      </View>
      <View style={{ flex: 1 }}>
        <Txt style={{ fontWeight: "700" }}>{label}</Txt>
        {hint ? <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>{hint}</Txt> : null}
      </View>
      <Txt style={styles.rankNum}>#{value}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border },
  hero: { flexDirection: "row", alignItems: "center", padding: 18, borderRadius: radius.xxl, marginBottom: 16, minHeight: 130 },
  heroLabel: { color: "rgba(255,255,255,0.95)", fontWeight: "700", letterSpacing: 0.5, fontSize: 12 },
  heroValue: { color: "#fff", fontSize: 44, fontWeight: "900", lineHeight: 50 },
  heroSub: { color: "rgba(255,255,255,0.95)", marginTop: 4, fontSize: 12, fontWeight: "600" },
  tpsPill: { flexDirection: "row", alignItems: "baseline", backgroundColor: "#fff", paddingHorizontal: 16, paddingVertical: 8, borderRadius: 14, shadowColor: "#000", shadowOpacity: 0.18, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 4 },
  tpsValue: { fontSize: 32, fontWeight: "900", color: "#1A1A2E" },
  tpsMax: { fontSize: 14, fontWeight: "700", color: colors.textSecondary, marginLeft: 4 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  statCard: { width: "48%", flexDirection: "row", alignItems: "center", padding: 12, borderRadius: radius.lg, gap: 10 },
  statIcon: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  rankRow: { flexDirection: "row", alignItems: "center", paddingVertical: 12, gap: 12 },
  rankRowBorder: { borderBottomWidth: 1, borderBottomColor: colors.border },
  rankIcon: { width: 36, height: 36, borderRadius: 12, backgroundColor: colors.primary + "1F", alignItems: "center", justifyContent: "center" },
  rankNum: { fontWeight: "800", fontSize: 18, color: colors.primary },
  openLb: { flexDirection: "row", alignItems: "center", justifyContent: "center", paddingVertical: 12, marginTop: 14, gap: 6, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primary + "0F" },
  openLbText: { fontWeight: "700", color: colors.primary },
});
