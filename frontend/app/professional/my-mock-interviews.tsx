import React, { useEffect, useState, useCallback, useMemo } from "react";
import { View, StyleSheet, TouchableOpacity, Linking } from "react-native";
import { webSafeAlert } from "@/src/lib/webSafeAlert";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

type Booking = {
  id: string;
  candidate_name?: string;
  student_name?: string;
  start_at: string;
  end_at: string;
  status: string;
  skill_set?: string[];
  meeting_url?: string;
  candidate_rating?: number;
  feedback?: string;
  join_enabled?: boolean;
  slot_ended?: boolean;
  both_joined?: boolean;
};

function fmtDate(d: string) {
  try { return new Date(d).toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", year: "numeric" }); } catch { return "—"; }
}
function fmtTime(d: string) {
  try { return new Date(d).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", hour12: true }); } catch { return "—"; }
}

export default function ProMyMockInterviews() {
  const router = useRouter();
  const [tab, setTab] = useState<"upcoming" | "completed">("upcoming");
  const [items, setItems] = useState<Booking[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await api<Booking[]>(`/interviews/my-bookings?upcoming_only=false`);
      setItems(r || []);
    } catch {}
    setRefreshing(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const upcoming = useMemo(() => items.filter((b) => b.status === "booked" || b.status === "upcoming"), [items]);
  const completed = useMemo(() => items.filter((b) => b.status === "completed"), [items]);
  const data = tab === "upcoming" ? upcoming : completed;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={["top"]}>
      <View style={styles.header}>
        <TouchableOpacity testID="back-btn" onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="chevron-back" size={28} color={colors.textPrimary} />
        </TouchableOpacity>
        <Txt variant="h3">My Mock Interviews</Txt>
        <View style={{ width: 28 }} />
      </View>

      <View style={styles.tabsRow}>
        <Tab testID="tab-upcoming" active={tab === "upcoming"} label={`Upcoming (${upcoming.length})`} onPress={() => setTab("upcoming")} />
        <Tab testID="tab-completed" active={tab === "completed"} label={`Completed (${completed.length})`} onPress={() => setTab("completed")} />
      </View>

      <Screen refreshing={refreshing} onRefresh={load} noPad>
        <View style={{ padding: 20, paddingTop: 4, gap: 10 }}>
          {data.length === 0 ? (
            <Card>
              <Txt variant="muted">
                {tab === "upcoming" ? "No upcoming interviews. Create a slot from the Interviews tab." : "No completed interviews to review yet."}
              </Txt>
            </Card>
          ) : null}
          {data.map((b) => tab === "upcoming" ? (
            <UpcomingRow
              key={b.id}
              b={b}
              onJoin={() => {
                // Iter 69: Join is allowed only within 10 min before start until slot end.
                // Backend's `join_enabled` encodes the window.
                if (!b.join_enabled) {
                  webSafeAlert(
                    "Join Meeting Not Available",
                    "You can join the meeting only 10 minutes before the scheduled interview time. Please try again later.",
                  );
                  return;
                }
                if (b.meeting_url) Linking.openURL(b.meeting_url).catch(() => router.push(`/video/${b.id}`));
                else router.push(`/video/${b.id}`);
              }}
              onProvideFeedback={() => router.push("/professional/slots")}
            />
          ) : (
            <CompletedRow key={b.id} b={b} />
          ))}
        </View>
      </Screen>
    </SafeAreaView>
  );
}

function Tab({ active, label, onPress, testID }: { active: boolean; label: string; onPress: () => void; testID?: string }) {
  return (
    <TouchableOpacity testID={testID} onPress={onPress} style={[styles.tab, active && styles.tabActive]}>
      <Txt style={{ fontWeight: "700", color: active ? "#7C3AED" : colors.textSecondary }}>{label}</Txt>
    </TouchableOpacity>
  );
}

function UpcomingRow({ b, onJoin, onProvideFeedback }: { b: Booking; onJoin: () => void; onProvideFeedback: () => void }) {
  const candidateName = b.candidate_name || b.student_name || "Candidate";
  const slotEnded = !!b.slot_ended;
  const bothJoined = !!b.both_joined;

  // CTA decision tree:
  //   1. Slot still active + join window open      → Join interview (purple)
  //   2. Slot still active + window not open yet   → no button (just Scheduled pill)
  //   3. Slot has ended + both parties joined      → Provide feedback (orange)
  //   4. Slot has ended + at least one no-show     → Completed (disabled grey)
  let cta: "join" | "feedback" | "completed" | "none" = "none";
  if (slotEnded) {
    cta = bothJoined ? "feedback" : "completed";
  } else if (b.join_enabled || !!b.meeting_url) {
    cta = "join";
  }

  // Status pill text mirrors the CTA state.
  const pillLabel = slotEnded
    ? (bothJoined ? "Awaiting Review" : "Completed")
    : (b.join_enabled ? "Ready" : (b.status === "booked" ? "Booked" : (b.status || "Scheduled")));
  const pillColor = slotEnded
    ? (bothJoined ? "#F59E0B" : colors.textSecondary)
    : (b.join_enabled ? colors.success : "#7C3AED");

  return (
    <Card>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
        <View style={{ flex: 1 }}>
          <Txt variant="h3">{candidateName}</Txt>
          {b.skill_set?.length ? (
            <View style={styles.metaRow}>
              <Ionicons name="briefcase" size={13} color={"#7C3AED"} />
              <Txt variant="small" style={styles.metaText} numberOfLines={1}>{b.skill_set.join(", ")}</Txt>
            </View>
          ) : null}
          <View style={styles.metaRow}>
            <Ionicons name="calendar" size={13} color={colors.textSecondary} />
            <Txt variant="small" style={styles.metaText}>{fmtDate(b.start_at)}</Txt>
          </View>
          <View style={styles.metaRow}>
            <Ionicons name="time" size={13} color={colors.textSecondary} />
            <Txt variant="small" style={styles.metaText}>{fmtTime(b.start_at)} – {fmtTime(b.end_at)}</Txt>
          </View>
        </View>
        <View style={[styles.statusPill, { backgroundColor: pillColor }]}>
          <Txt variant="small" style={{ color: "#fff", fontWeight: "700", textTransform: "capitalize" }}>{pillLabel}</Txt>
        </View>
      </View>
      {cta === "join" ? (
        <TouchableOpacity testID={`join-${b.id}`} onPress={onJoin} style={[styles.joinBtn, !b.join_enabled && { opacity: 0.65 }]}>
          <Ionicons name="videocam" size={16} color="#fff" />
          <Txt style={{ color: "#fff", fontWeight: "700", marginLeft: 6 }}>Join interview</Txt>
        </TouchableOpacity>
      ) : cta === "feedback" ? (
        <TouchableOpacity testID={`feedback-${b.id}`} onPress={onProvideFeedback} style={[styles.joinBtn, { backgroundColor: "#F59E0B" }]}>
          <Ionicons name="create" size={16} color="#fff" />
          <Txt style={{ color: "#fff", fontWeight: "700", marginLeft: 6 }}>Provide feedback</Txt>
        </TouchableOpacity>
      ) : cta === "completed" ? (
        <View testID={`completed-disabled-${b.id}`} style={[styles.joinBtn, styles.disabledBtn]}>
          <Ionicons name="checkmark-circle" size={16} color={colors.textSecondary} />
          <Txt style={{ color: colors.textSecondary, fontWeight: "700", marginLeft: 6 }}>Completed</Txt>
        </View>
      ) : null}
    </Card>
  );
}

function CompletedRow({ b }: { b: Booking }) {
  const candidateName = b.candidate_name || b.student_name || "Candidate";
  return (
    <Card>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
        <View style={{ flex: 1 }}>
          <Txt variant="h3">{candidateName}</Txt>
          {b.skill_set?.length ? (
            <View style={styles.metaRow}>
              <Ionicons name="briefcase" size={13} color={"#7C3AED"} />
              <Txt variant="small" style={styles.metaText} numberOfLines={1}>{b.skill_set.join(", ")}</Txt>
            </View>
          ) : null}
          <View style={styles.metaRow}>
            <Ionicons name="calendar" size={13} color={colors.textSecondary} />
            <Txt variant="small" style={styles.metaText}>{fmtDate(b.start_at)}</Txt>
          </View>
        </View>
        <View style={[styles.statusPill, { backgroundColor: colors.success }]}>
          <Txt variant="small" style={{ color: "#fff", fontWeight: "700" }}>Completed</Txt>
        </View>
      </View>
      <View style={styles.feedbackBox}>
        <View style={styles.ratingsRow}>
          <RatingChip label="Overall" value={b.candidate_rating} icon="star" color="#F59E0B" />
          <RatingChip label="Technical" value={null} icon="construct" color="#2563EB" />
          <RatingChip label="Communication" value={null} icon="chatbubble-ellipses" color="#7C3AED" />
        </View>
        {b.feedback ? (
          <View style={{ marginTop: 10 }}>
            <Txt variant="label" style={{ color: colors.textSecondary, marginBottom: 4 }}>Feedback you submitted</Txt>
            <Txt style={{ color: colors.textPrimary, lineHeight: 20 }}>{b.feedback}</Txt>
          </View>
        ) : (
          <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 8, fontStyle: "italic" }}>No written feedback yet.</Txt>
        )}
      </View>
    </Card>
  );
}

function RatingChip({ label, value, icon, color }: { label: string; value?: number | null; icon: any; color: string }) {
  const display = value != null ? `${value}/10` : "—";
  return (
    <View style={[styles.ratingChip, { backgroundColor: color + "12" }]}>
      <Ionicons name={icon} size={14} color={color} />
      <View style={{ marginLeft: 6 }}>
        <Txt style={{ fontSize: 10, fontWeight: "700", color }}>{label}</Txt>
        <Txt style={{ fontSize: 13, fontWeight: "800", color: colors.textPrimary, marginTop: 1 }}>{display}</Txt>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border },
  tabsRow: { flexDirection: "row", paddingHorizontal: 20, paddingTop: 12, gap: 8 },
  tab: { flex: 1, paddingVertical: 12, alignItems: "center", borderBottomWidth: 2, borderBottomColor: "transparent" },
  tabActive: { borderBottomColor: "#7C3AED" },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  metaText: { color: colors.textSecondary, flexShrink: 1 },
  statusPill: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 12 },
  joinBtn: { marginTop: 10, flexDirection: "row", alignItems: "center", justifyContent: "center", backgroundColor: "#7C3AED", paddingVertical: 10, borderRadius: radius.lg },
  disabledBtn: { backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border },
  feedbackBox: { marginTop: 12, padding: 12, borderRadius: radius.lg, backgroundColor: colors.surfaceAlt },
  ratingsRow: { flexDirection: "row", gap: 6 },
  ratingChip: { flex: 1, flexDirection: "row", alignItems: "center", padding: 8, borderRadius: 10 },
});
