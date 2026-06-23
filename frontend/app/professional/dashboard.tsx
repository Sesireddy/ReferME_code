import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function ProDashboard() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [rank, setRank] = useState<number | null>(null);
  const [rating, setRating] = useState<{ rating: number; count: number }>({ rating: 0, count: 0 });
  const [bookings, setBookings] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const me = await api<{ user: any }>("/auth/me");
      setUser(me.user);
      const lb = await api<any[]>("/leaderboard/professionals");
      const meRow = lb.find((x) => x.is_me);
      setRank(meRow?.rank ?? null);
      setRating({
        rating: meRow?.rating ?? 0,
        count: meRow?.ratings_count ?? 0,
      });
      try {
        const bk = await api<any[]>("/interviews/my-bookings");
        setBookings(bk || []);
      } catch {}
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

      {/* Hero: stats + rating — NO credit balance here (Profile → Wallet only) */}
      <LinearGradient colors={["#7C3AED", "#A855F7"]} start={{x:0,y:0}} end={{x:1,y:1}} style={styles.hero}>
        <View style={{ flex: 1 }}>
          <Txt style={{ color: "#fff", opacity: 0.85 }} variant="label">Your impact</Txt>
          <View style={{ flexDirection: "row", marginTop: 8, alignItems: "baseline" }}>
            <Txt style={{ color: "#fff", fontSize: 36, fontWeight: "800" }}>{user?.interviews_conducted ?? 0}</Txt>
            <Txt style={{ color: "#fff", fontSize: 14, opacity: 0.85, marginLeft: 6 }}>interviews</Txt>
            <Txt style={{ color: "#fff", fontSize: 36, fontWeight: "800", marginLeft: 18 }}>{user?.referrals_made ?? 0}</Txt>
            <Txt style={{ color: "#fff", fontSize: 14, opacity: 0.85, marginLeft: 6 }}>referrals</Txt>
          </View>
          <View style={{ flexDirection: "row", marginTop: 10, alignItems: "center" }}>
            <Ionicons name="star" size={18} color="#FFD566" />
            <Txt style={{ color: "#fff", marginLeft: 6, fontWeight: "700" }}>
              {rating.rating ? `${rating.rating.toFixed(1)}/10` : "No ratings yet"}
            </Txt>
            {rating.count > 0 ? (
              <Txt style={{ color: "#fff", opacity: 0.8, marginLeft: 6 }} variant="small">
                ({rating.count} review{rating.count > 1 ? "s" : ""})
              </Txt>
            ) : null}
          </View>
        </View>
        <View style={styles.heroIcon}>
          <Ionicons name="ribbon" size={56} color="#fff" />
        </View>
      </LinearGradient>

      <Card style={{ marginTop: 12, display: "none" }}>
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
        <TouchableOpacity testID="cta-conduct" style={styles.tile} onPress={() => router.push("/professional/slots")}>
          <Card style={[styles.tileCard, { borderColor: "#7C3AED", borderWidth: 2 }]}>
            <Ionicons name="videocam" size={24} color="#7C3AED" />
            <Txt variant="h3" style={{ marginTop: 8 }}>Conduct Interview</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>+35 credits / session</Txt>
          </Card>
        </TouchableOpacity>
        <TouchableOpacity testID="cta-post-job" style={styles.tile} onPress={() => router.push("/professional/post-job")}>
          <Card style={[styles.tileCard, { borderColor: colors.primary, borderWidth: 2 }]}>
            <Ionicons name="briefcase" size={24} color={colors.primary} />
            <Txt variant="h3" style={{ marginTop: 8 }}>Post a Job</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>+100 at 4 apps</Txt>
          </Card>
        </TouchableOpacity>
      </View>

      <View style={styles.row}>
        <TouchableOpacity testID="cta-my-jobs" style={styles.tile} onPress={() => router.push("/professional/my-jobs")}>
          <Card style={[styles.tileCard, { borderColor: colors.secondary, borderWidth: 2 }]}>
            <Ionicons name="folder-open" size={24} color={colors.textPrimary} />
            <Txt variant="h3" style={{ marginTop: 8 }}>My Posted Jobs</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>Manage applicants</Txt>
          </Card>
        </TouchableOpacity>
        <TouchableOpacity testID="cta-refer" style={styles.tile} onPress={() => router.push("/professional/my-jobs")}>
          <Card style={[styles.tileCard, { borderColor: "#FFD566", borderWidth: 2 }]}>
            <Ionicons name="share-social" size={24} color={colors.textPrimary} />
            <Txt variant="h3" style={{ marginTop: 8 }}>Refer Candidate</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>+₹1500/hire</Txt>
          </Card>
        </TouchableOpacity>
      </View>

      {bookings.length > 0 ? (
        <Card style={{ marginTop: 16 }}>
          <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 8 }}>
            <Ionicons name="videocam" size={20} color="#7C3AED" />
            <Txt variant="h3" style={{ marginLeft: 8 }}>Upcoming sessions</Txt>
          </View>
          {bookings.slice(0, 3).map((b: any) => {
            const start = b.start_at ? new Date(b.start_at) : null;
            return (
              <View key={b.id} style={{ paddingVertical: 10, borderTopWidth: 1, borderTopColor: colors.border }}>
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                  <View style={{ flex: 1, marginRight: 8 }}>
                    <Txt variant="h3" numberOfLines={1}>{b.counterparty_name || b.student_name || "Candidate"}</Txt>
                    <Txt variant="small" style={{ color: colors.textSecondary }}>
                      {start ? start.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit", month: "short", day: "numeric" }) : ""}
                    </Txt>
                    {(b.skill_set || []).length ? (
                      <Txt variant="small" style={{ color: colors.textSecondary }}>{(b.skill_set || []).join(", ")}</Txt>
                    ) : null}
                  </View>
                  <Button
                    testID={`pro-join-${b.id}`}
                    title={b.join_enabled ? "Join" : "Details"}
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
    </Screen>
  );
}
const styles = StyleSheet.create({
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 16 },
  iconBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  hero: { padding: 20, borderRadius: radius.xxl, flexDirection: "row", alignItems: "center" },
  heroIcon: { width: 80, alignItems: "center", justifyContent: "center", opacity: 0.85 },
  row: { flexDirection: "row", gap: 12, marginTop: 12, alignItems: "stretch" },
  tile: { flex: 1 },
  tileCard: { flex: 1, justifyContent: "flex-start" },
  rankIcon: { width: 56, height: 56, borderRadius: 18, alignItems: "center", justifyContent: "center" },
});
