import React, { useEffect, useState, useCallback, useMemo } from "react";
import { View, StyleSheet, TouchableOpacity, Linking } from "react-native";
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
  pro_id: string;
  pro_name?: string;
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
  try {
    return new Date(d).toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  } catch { return "—"; }
}
function fmtTime(d: string) {
  try {
    return new Date(d).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", hour12: true });
  } catch { return "—"; }
}

export default function MyMockInterviews() {
  const router = useRouter();
  const [tab, setTab] = useState<"upcoming" | "completed">("upcoming");
  const [items, setItems] = useState<Booking[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      // upcoming_only=false gives us full history; we split client-side by status.
      const r = await api<Booking[]>(`/interviews/my-bookings?upcoming_only=false`);
      setItems(r || []);
    } catch {}
    setRefreshing(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const upcoming = useMemo(
    // Only active bookings (not ended yet) belong on the Upcoming tab.
    // Past booked-but-not-completed slots get rolled into Completed below.
    () => items.filter((b) => (b.status === "booked" || b.status === "upcoming") && !b.slot_ended),
    [items],
  );
  const completed = useMemo(
    // Completed tab includes:
    //   (a) slots the pro has marked as completed (with feedback)
    //   (b) ended booked slots that were never completed (no-show OR pro forgot to mark done)
    () => items.filter((b) => b.status === "completed" || ((b.status === "booked" || b.status === "upcoming") && b.slot_ended)),
    [items],
  );

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
        <Tab
          testID="tab-upcoming"
          active={tab === "upcoming"}
          label={`Upcoming (${upcoming.length})`}
          onPress={() => setTab("upcoming")}
        />
        <Tab
          testID="tab-completed"
          active={tab === "completed"}
          label={`Completed (${completed.length})`}
          onPress={() => setTab("completed")}
        />
      </View>

      <Screen refreshing={refreshing} onRefresh={load} noPad>
        <View style={{ padding: 20, paddingTop: 4, gap: 10 }}>
          {data.length === 0 ? (
            <Card>
              <Txt variant="muted">
                {tab === "upcoming"
                  ? "No upcoming interviews yet. Book one from the Interviews tab."
                  : "No completed interviews to review yet."}
              </Txt>
            </Card>
          ) : null}

          {data.map((b) =>
            tab === "upcoming" ? (
              <UpcomingRow key={b.id} b={b} onJoin={() => {
                if (b.join_enabled) router.push(`/video/${b.id}`);
                else if (b.meeting_url) Linking.openURL(b.meeting_url).catch(() => {});
              }} />
            ) : (
              <CompletedRow key={b.id} b={b} />
            )
          )}
        </View>
      </Screen>
    </SafeAreaView>
  );
}

function Tab({ active, label, onPress, testID }: { active: boolean; label: string; onPress: () => void; testID?: string }) {
  return (
    <TouchableOpacity testID={testID} onPress={onPress} style={[styles.tab, active && styles.tabActive]}>
      <Txt style={{ fontWeight: "700", color: active ? colors.primary : colors.textSecondary }}>{label}</Txt>
    </TouchableOpacity>
  );
}

function UpcomingRow({ b, onJoin }: { b: Booking; onJoin: () => void }) {
  // Upcoming list now only contains non-ended slots, so Join can be safely shown
  // when within the join window. Guard against slot_ended just in case.
  const canJoin = !b.slot_ended && (b.join_enabled || !!b.meeting_url);
  return (
    <Card>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
        <View style={{ flex: 1 }}>
          <Txt variant="h3">{b.pro_name || "Professional"}</Txt>
          {b.skill_set?.length ? (
            <View style={styles.metaRow}>
              <Ionicons name="briefcase" size={13} color={"#7C3AED"} />
              <Txt variant="small" style={styles.metaText} numberOfLines={1}>
                {b.skill_set.join(", ")}
              </Txt>
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
        <View style={[styles.statusPill, { backgroundColor: b.join_enabled ? colors.success : colors.primary }]}>
          <Txt variant="small" style={{ color: "#fff", fontWeight: "700", textTransform: "capitalize" }}>
            {b.join_enabled ? "Ready" : b.status}
          </Txt>
        </View>
      </View>
      {canJoin ? (
        <TouchableOpacity testID={`join-${b.id}`} onPress={onJoin} style={styles.joinBtn}>
          <Ionicons name="videocam" size={16} color="#fff" />
          <Txt style={{ color: "#fff", fontWeight: "700", marginLeft: 6 }}>Join interview</Txt>
        </TouchableOpacity>
      ) : null}
    </Card>
  );
}

function CompletedRow({ b }: { b: Booking }) {
  // Spec: enabled "View feedback" only when (a) the slot was actually completed by the pro
  // (status === 'completed') — which implies feedback exists — AND (b) both parties joined.
  // For everything else (no-show, or pro never marked completed), show disabled "Completed".
  const hasFeedback = b.status === "completed" && !!(b.feedback || b.candidate_rating != null);
  const canViewFeedback = hasFeedback && !!b.both_joined;
  const [open, setOpen] = useState(false);

  let badgeText = "Completed";
  let badgeColor: string = colors.textSecondary;
  if (canViewFeedback) {
    badgeText = "Reviewed";
    badgeColor = colors.success;
  } else if (b.both_joined === false && b.status !== "completed") {
    badgeText = "No-show";
    badgeColor = colors.textSecondary;
  }

  return (
    <Card>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
        <View style={{ flex: 1 }}>
          <Txt variant="h3">{b.pro_name || "Professional"}</Txt>
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
        <View style={[styles.statusPill, { backgroundColor: badgeColor }]}>
          <Txt variant="small" style={{ color: "#fff", fontWeight: "700" }}>{badgeText}</Txt>
        </View>
      </View>

      {canViewFeedback ? (
        <>
          <TouchableOpacity
            testID={`view-feedback-${b.id}`}
            onPress={() => setOpen((v) => !v)}
            style={styles.feedbackBtn}
          >
            <Ionicons name={open ? "chevron-up" : "document-text"} size={16} color="#fff" />
            <Txt style={{ color: "#fff", fontWeight: "700", marginLeft: 6 }}>
              {open ? "Hide feedback" : "View feedback"}
            </Txt>
          </TouchableOpacity>
          {open ? (
            <View style={styles.feedbackBox}>
              <View style={styles.ratingsRow}>
                <RatingChip label="Overall" value={b.candidate_rating} icon="star" color="#F59E0B" />
                <RatingChip label="Technical" value={null} icon="construct" color="#2563EB" placeholder="—" />
                <RatingChip label="Communication" value={null} icon="chatbubble-ellipses" color="#7C3AED" placeholder="—" />
              </View>
              {b.feedback ? (
                <View style={{ marginTop: 10 }}>
                  <Txt variant="label" style={{ color: colors.textSecondary, marginBottom: 4 }}>Professional Feedback</Txt>
                  <Txt style={{ color: colors.textPrimary, lineHeight: 20 }}>{b.feedback}</Txt>
                </View>
              ) : (
                <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 8, fontStyle: "italic" }}>
                  No written feedback was provided.
                </Txt>
              )}
            </View>
          ) : null}
        </>
      ) : (
        <View testID={`completed-disabled-${b.id}`} style={[styles.feedbackBtn, styles.feedbackBtnDisabled]}>
          <Ionicons name="checkmark-circle" size={16} color={colors.textSecondary} />
          <Txt style={{ color: colors.textSecondary, fontWeight: "700", marginLeft: 6 }}>Completed</Txt>
        </View>
      )}
    </Card>
  );
}

function RatingChip({ label, value, icon, color, placeholder }: { label: string; value?: number | null; icon: any; color: string; placeholder?: string }) {
  const display = value != null ? `${value}/10` : (placeholder || "—");
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
  tabActive: { borderBottomColor: colors.primary },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  metaText: { color: colors.textSecondary, flexShrink: 1 },
  statusPill: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 12 },
  joinBtn: { marginTop: 10, flexDirection: "row", alignItems: "center", justifyContent: "center", backgroundColor: colors.primary, paddingVertical: 10, borderRadius: radius.lg },
  feedbackBtn: { marginTop: 10, flexDirection: "row", alignItems: "center", justifyContent: "center", backgroundColor: colors.success, paddingVertical: 10, borderRadius: radius.lg },
  feedbackBtnDisabled: { backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border },
  feedbackBox: { marginTop: 12, padding: 12, borderRadius: radius.lg, backgroundColor: colors.surfaceAlt },
  ratingsRow: { flexDirection: "row", gap: 6 },
  ratingChip: { flex: 1, flexDirection: "row", alignItems: "center", padding: 8, borderRadius: 10 },
  improvementsHint: { color: colors.textSecondary, marginTop: 10, fontSize: 11, textAlign: "center" },
});
