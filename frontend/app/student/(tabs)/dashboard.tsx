import React, { useEffect, useState, useCallback, useRef } from "react";
import { View, StyleSheet, TouchableOpacity } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons, FontAwesome5 } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { successAlert } from "@/src/lib/successAlert";
import { tryJoinMeeting } from "@/src/lib/joinMeeting";

export default function StudentDashboard() {
  const router = useRouter();
  const params = useLocalSearchParams<{ welcome_bonus?: string }>();
  const welcomeShownRef = useRef(false);
  const [user, setUser] = useState<any>(null);
  const [profile, setProfile] = useState<any>(null);
  const [rank, setRank] = useState<number | null>(null);
  const [ranks, setRanks] = useState<{ overall_rank?: number; category_rank?: number | null; skill_rank?: number | null; primary_skill?: string | null; category_label?: string | null } | null>(null);
  const [bookings, setBookings] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

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

  // One-time Signup Bonus Welcome popup for newly-registered Job Seekers
  useEffect(() => {
    const bonus = Number(params.welcome_bonus || 0);
    if (bonus > 0 && !welcomeShownRef.current) {
      welcomeShownRef.current = true;
      // Defer to next tick so the screen is mounted before the modal opens
      setTimeout(() => {
        successAlert.show({
          title: "🎉 Welcome to ReferME!",
          message: `${bonus} Credits have been added to your wallet as a Signup Bonus.\n\nUse these credits to apply for jobs and book mock interviews.`,
          okLabel: "OK",
          intent: "success",
          onOk: () => {
            // Clear the welcome_bonus param so it doesn't re-trigger on remount/back
            router.setParams({ welcome_bonus: "" });
          },
        });
      }, 200);
    }
  }, [params.welcome_bonus, router]);

  const score = profile?.resume_score ?? 0;
  const tps: number = Number(profile?.tps ?? 0);
  const interviewsAttended: number = Number(user?.interviews_attended ?? 0);
  const avgRating: number = Number(user?.student_rating ?? 0); // 0..10
  const freeUses = user?.free_uses_left ?? 0;

  // TPS components (same logic as backend compute_tps)
  const interviewBucket = interviewsAttended <= 0 ? 0 : interviewsAttended <= 2 ? 15 : interviewsAttended <= 5 ? 25 : 30;
  const interviewPct = (interviewBucket / 30) * 100;
  const ratingPct = avgRating > 0 ? (avgRating / 10) * 100 : 0;
  const resumeContribution = score * 0.6;        // out of 60
  const interviewContribution = interviewPct * 0.2; // out of 20
  const ratingContribution = ratingPct * 0.2;       // out of 20

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

      {/* Hero card: Talent Potential Score (TPS) breakdown */}
      <LinearGradient
        colors={["#FF5A5F", "#FFB347"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.heroCard}
      >
        <View style={styles.heroContent}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Ionicons name="trophy" size={14} color="#fff" />
            <Txt
              style={{ color: "#fff", opacity: 0.9, fontWeight: "700", letterSpacing: 0.5 }}
              variant="label"
              numberOfLines={1}
              adjustsFontSizeToFit
            >
              TALENT POTENTIAL SCORE
            </Txt>
          </View>
          <View style={styles.tpsPill}>
            <Txt
              style={styles.tpsPillValue}
              numberOfLines={1}
              testID="student-tps"
            >
              {Math.round(tps)}
            </Txt>
            <Txt style={styles.tpsPillMax} numberOfLines={1}>/100</Txt>
          </View>

          {/* Single composite progress bar */}
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${Math.min(100, tps)}%` }]} />
          </View>

          {/* Breakdown chips */}
          <View style={styles.breakdownRow}>
            <BreakdownChip
              icon="document-text"
              label="Resume"
              contribution={resumeContribution}
              maxContribution={60}
              detail={`${score}/100`}
            />
            <BreakdownChip
              icon="videocam"
              label="Interviews"
              contribution={interviewContribution}
              maxContribution={20}
              detail={`${interviewsAttended} attended`}
            />
            <BreakdownChip
              icon="star"
              label="Rating"
              contribution={ratingContribution}
              maxContribution={20}
              detail={avgRating > 0 ? `★ ${avgRating.toFixed(1)}/10` : "No ratings"}
            />
          </View>
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
        <TouchableOpacity testID="cta-apply-job" style={styles.tile} onPress={() => router.push("/student/jobs")}>
          <Card style={[styles.tileCard, { borderColor: colors.primary, borderWidth: 2 }]}>
            <View style={[styles.actionIcon, { backgroundColor: "#FFE4E5" }]}>
              <FontAwesome5 name="handshake" size={20} color={colors.primary} />
            </View>
            <Txt variant="h3" style={{ marginTop: 12 }}>Apply for Referral</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>Top companies</Txt>
          </Card>
        </TouchableOpacity>
      </View>

      <TouchableOpacity testID="walkin-jobs-tile" activeOpacity={0.85} onPress={() => router.push("/student/walkin-jobs")}>
        <Card style={{ marginTop: 16 }}>
          <View style={{ flexDirection: "row", alignItems: "center" }}>
            <View style={[styles.rankIcon, { backgroundColor: "#E0F2FE" }]}>
              <Ionicons name="megaphone" size={26} color="#2563EB" />
            </View>
            <View style={{ flex: 1, marginLeft: 14 }}>
              <Txt variant="label">Walk-in & Direct Jobs</Txt>
              <Txt variant="h3" style={{ marginTop: 2 }}>Free · Admin curated</Txt>
              <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                Walk-in drives, mass hiring, campus & direct openings
              </Txt>
            </View>
            <Ionicons name="chevron-forward" size={22} color={colors.textSecondary} />
          </View>
        </Card>
      </TouchableOpacity>

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
                    title="Join Meeting"
                    variant={b.join_enabled ? "primary" : "secondary"}
                    onPress={() => tryJoinMeeting(b, router)}
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
  heroCard: { borderRadius: radius.xxl, padding: 18, marginBottom: 16, minHeight: 150 },
  heroContent: { flex: 1, minWidth: 0 },
  heroIcon: { width: 56, height: 56, alignItems: "center", justifyContent: "center", opacity: 0.9, marginLeft: 8 },
  progressTrack: { height: 8, backgroundColor: "rgba(255,255,255,0.25)", borderRadius: 8, marginTop: 12, overflow: "hidden" },
  progressFill: { height: "100%", backgroundColor: "#fff", borderRadius: 8 },
  tpsPill: {
    flexDirection: "row",
    alignItems: "baseline",
    alignSelf: "flex-start",
    backgroundColor: "#fff",
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 14,
    marginTop: 8,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.22,
    shadowRadius: 10,
    elevation: 6,
  },
  tpsPillValue: { fontSize: 44, fontWeight: "900", color: "#1A1A2E", lineHeight: 50 },
  tpsPillMax: { fontSize: 18, fontWeight: "700", color: "#6B7280", marginLeft: 6 },
  breakdownRow: { flexDirection: "row", gap: 8, marginTop: 14 },
  breakdownChip: {
    flex: 1,
    backgroundColor: "rgba(255,255,255,0.18)",
    borderRadius: 12,
    paddingVertical: 8,
    paddingHorizontal: 8,
    minHeight: 78,
  },
  breakdownLabel: { color: "#fff", fontSize: 10, fontWeight: "700", opacity: 0.95 },
  breakdownValue: { color: "#fff", fontWeight: "800", fontSize: 15, marginTop: 4 },
  breakdownDetail: { color: "#fff", fontSize: 10, opacity: 0.85, marginTop: 2 },
  miniTrack: { height: 4, backgroundColor: "rgba(255,255,255,0.25)", borderRadius: 4, marginTop: 6, overflow: "hidden" },
  miniFill: { height: "100%", backgroundColor: "#fff", borderRadius: 4 },
  actionRow: { flexDirection: "row", gap: 12, alignItems: "stretch" },
  tile: { flex: 1 },
  tileCard: { flex: 1, justifyContent: "flex-start" },
  actionIcon: { width: 44, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  rankIcon: { width: 56, height: 56, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  rankBox: { flex: 1, alignItems: "center", paddingVertical: 8, paddingHorizontal: 4 },
});

function BreakdownChip({ icon, label, contribution, maxContribution, detail }: { icon: any; label: string; contribution: number; maxContribution: number; detail: string }) {
  const pct = Math.max(0, Math.min(100, (contribution / maxContribution) * 100));
  return (
    <View style={styles.breakdownChip}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
        <Ionicons name={icon} size={11} color="#fff" />
        <Txt
          style={styles.breakdownLabel}
          numberOfLines={1}
          adjustsFontSizeToFit
          minimumFontScale={0.7}
        >
          {label}
        </Txt>
      </View>
      <Txt
        style={styles.breakdownValue}
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.7}
      >
        +{contribution.toFixed(1)}
      </Txt>
      <View style={styles.miniTrack}>
        <View style={[styles.miniFill, { width: `${pct}%` }]} />
      </View>
      <Txt
        style={styles.breakdownDetail}
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.7}
      >
        {detail}
      </Txt>
    </View>
  );
}
