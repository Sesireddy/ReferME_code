import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons, FontAwesome5 } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { ConfirmDialog } from "@/src/components/ConfirmDialog";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function StudentDashboard() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [profile, setProfile] = useState<any>(null);
  const [rank, setRank] = useState<number | null>(null);
  const [ranks, setRanks] = useState<{ overall_rank?: number; category_rank?: number | null; skill_rank?: number | null; primary_skill?: string | null; category_label?: string | null } | null>(null);
  const [bookings, setBookings] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [tooEarlyOpen, setTooEarlyOpen] = useState(false);

  function tryJoin(b: any) {
    if (b.join_enabled) {
      router.push(`/video/${b.id}`);
    } else {
      setTooEarlyOpen(true);
    }
  }

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const me = await api<{ user: any; profile: any }>("/auth/me");
      setUser(me.user);
      setProfile(me.profile || {});
      const lb = await api<{ items: any[] } | any[]>("/leaderboard/students");
      const items = Array.isArray(lb) ? lb : (lb?.items || []);
      const meRank = items.find((s: any) => s.is_me);
      setRank(meRank?.rank ?? null);
      try {
        const r = await api<any>("/leaderboard/student/me/ranks");
        setRanks(r);
      } catch {}
      try {
        const bk = await api<any[]>("/interviews/my-bookings");
        setBookings(bk || []);
      } catch {}
    } catch {
      // ignore
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const score = profile?.resume_score ?? 0;
  const freeUses = user?.free_uses_left ?? 0;

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Txt variant="label">Hello,</Txt>
          <Txt variant="h2" testID="student-name">{user?.name || (user?.email || "").split("@")[0]}</Txt>
        </View>
        <TouchableOpacity testID="notif-btn" onPress={() => router.push("/notifications")}>
          <View style={styles.iconBtn}>
            <Ionicons name="notifications" size={22} color={colors.textPrimary} />
          </View>
        </TouchableOpacity>
      </View>

      {/* Hero card: resume score + free uses — NO credits here (Profile → Wallet only) */}
      <LinearGradient
        colors={["#FF5A5F", "#FFB347"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.heroCard}
      >
        <View style={{ flex: 1 }}>
          <Txt style={{ color: "#fff", opacity: 0.85 }} variant="label">Resume Score</Txt>
          <View style={{ flexDirection: "row", alignItems: "baseline", marginTop: 4 }}>
            <Txt
              style={{ color: "#fff", fontSize: 44, fontWeight: "800" }}
              numberOfLines={1}
              adjustsFontSizeToFit
              testID="student-score"
            >
              {score}
            </Txt>
            <Txt style={{ color: "#fff", fontSize: 22, opacity: 0.85, marginLeft: 4 }} numberOfLines={1}> /100</Txt>
          </View>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${Math.min(100, score)}%` }]} />
          </View>
          <Txt style={{ color: "#fff", opacity: 0.95, marginTop: 8 }} variant="small">
            Improve your Resume Score by attending Mock Interviews
          </Txt>
        </View>
        <View style={styles.heroIcon}>
          <Ionicons name="rocket" size={48} color="#fff" />
        </View>
      </LinearGradient>

      <View style={styles.actionRow}>
        <TouchableOpacity
          testID="cta-book-interview"
          style={{ flex: 1 }}
          onPress={() => router.push("/student/mock-interviews")}
        >
          <Card style={{ borderColor: colors.secondary, borderWidth: 2 }}>
            <View style={[styles.actionIcon, { backgroundColor: "#F5FFD0" }]}>
              <FontAwesome5 name="user-tie" size={20} color={colors.textPrimary} />
            </View>
            <Txt variant="h3" style={{ marginTop: 12 }}>Book Mock Interview</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>Practice with pros</Txt>
          </Card>
        </TouchableOpacity>
        <TouchableOpacity testID="cta-apply-job" style={{ flex: 1 }} onPress={() => router.push("/student/jobs")}>
          <Card style={{ borderColor: colors.primary, borderWidth: 2 }}>
            <View style={[styles.actionIcon, { backgroundColor: "#FFE4E5" }]}>
              <FontAwesome5 name="handshake" size={20} color={colors.primary} />
            </View>
            <Txt variant="h3" style={{ marginTop: 12 }}>Apply for Referral</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>Top companies</Txt>
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

      {ranks ? (
        <Card style={{ marginTop: 16 }}>
          <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 8 }}>
            <Ionicons name="trending-up" size={20} color={colors.primary} />
            <Txt variant="h3" style={{ marginLeft: 8 }}>Your Rankings</Txt>
          </View>
          <View style={{ flexDirection: "row", marginTop: 6 }}>
            <View style={styles.rankBox}>
              <Txt variant="small" style={{ color: colors.textSecondary, textAlign: "center" }} numberOfLines={2}>Overall Rank</Txt>
              <Txt style={{ fontWeight: "800", fontSize: 18, marginTop: 4 }} numberOfLines={1} adjustsFontSizeToFit>
                {ranks.overall_rank ?? "—"}
              </Txt>
            </View>
            <View style={styles.rankBox}>
              <Txt variant="small" style={{ color: colors.textSecondary, textAlign: "center" }} numberOfLines={2}>Category Rank</Txt>
              <Txt style={{ fontWeight: "800", fontSize: 18, marginTop: 4 }} numberOfLines={1} adjustsFontSizeToFit>
                {ranks.category_rank ?? "—"}
              </Txt>
              {ranks.category_label ? (
                <Txt variant="small" style={{ color: colors.textSecondary, fontSize: 10, marginTop: 2 }} numberOfLines={1}>{ranks.category_label}</Txt>
              ) : null}
            </View>
            <View style={styles.rankBox}>
              <Txt variant="small" style={{ color: colors.textSecondary, textAlign: "center" }} numberOfLines={2}>Skill Set Rank</Txt>
              <Txt style={{ fontWeight: "800", fontSize: 18, marginTop: 4 }} numberOfLines={1} adjustsFontSizeToFit>
                {ranks.skill_rank ?? "—"}
              </Txt>
              {ranks.primary_skill ? (
                <Txt variant="small" style={{ color: colors.textSecondary, fontSize: 10, marginTop: 2 }} numberOfLines={1}>{ranks.primary_skill}</Txt>
              ) : null}
            </View>
          </View>
        </Card>
      ) : null}

      {bookings.length > 0 ? (
        <Card style={{ marginTop: 16 }}>
          <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 8 }}>
            <Ionicons name="videocam" size={20} color={colors.primary} />
            <Txt variant="h3" style={{ marginLeft: 8 }}>Upcoming sessions</Txt>
          </View>
          {bookings.slice(0, 3).map((b: any) => {
            const start = b.start_at ? new Date(b.start_at) : null;
            return (
              <View key={b.id} style={{ paddingVertical: 10, borderTopWidth: 1, borderTopColor: colors.border }}>
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                  <View style={{ flex: 1, marginRight: 8 }}>
                    <Txt variant="h3" numberOfLines={1}>{b.counterparty_name || b.pro_name || "Mock Interview"}</Txt>
                    <Txt variant="small" style={{ color: colors.textSecondary }}>
                      {start ? start.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit", month: "short", day: "numeric" }) : ""}
                    </Txt>
                    {(b.skill_set || []).length ? (
                      <Txt variant="small" style={{ color: colors.textSecondary }}>{(b.skill_set || []).join(", ")}</Txt>
                    ) : null}
                  </View>
                  <Button
                    testID={`join-${b.id}`}
                    title={b.join_enabled ? "Join Meeting" : "Join Meeting"}
                    variant={b.join_enabled ? "primary" : "secondary"}
                    onPress={() => router.push(`/video/${b.id}`)}
                    style={{ height: 38, paddingHorizontal: 16 }}
                  />
                </View>
              </View>
            );
          })}
        </Card>
      ) : null}

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
  heroCard: { borderRadius: radius.xxl, padding: 20, flexDirection: "row", alignItems: "center", marginBottom: 16, minHeight: 160 },
  heroIcon: { width: 80, height: 80, alignItems: "center", justifyContent: "center", opacity: 0.85 },
  progressTrack: { height: 8, backgroundColor: "rgba(255,255,255,0.25)", borderRadius: 8, marginTop: 12, overflow: "hidden" },
  progressFill: { height: "100%", backgroundColor: "#fff", borderRadius: 8 },
  actionRow: { flexDirection: "row", gap: 12 },
  actionIcon: { width: 44, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  rankIcon: { width: 56, height: 56, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  rankBox: { flex: 1, alignItems: "center", paddingVertical: 8, paddingHorizontal: 4 },
});
