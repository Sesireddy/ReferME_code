import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, ActivityIndicator, Image } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

const STATUS_ORDER = ["applied", "shortlisted", "referred", "awaiting_interview", "interview_scheduled", "hired"];

export default function ApplicationDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [appdoc, setAppdoc] = useState<any>(null);
  const [job, setJob] = useState<any>(null);
  const [timeline, setTimeline] = useState<{ current_status: string; history: any[]; pending_changes: any[] } | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const apps = await api<any[]>("/applications");
      const a = apps.find((x) => x.id === id);
      if (a) {
        setAppdoc(a);
        const [j, tl] = await Promise.all([
          api<any>(`/jobs/${a.job_id}`).catch(() => null),
          api<any>(`/applications/${id}/timeline`).catch(() => null),
        ]);
        setJob(j);
        setTimeline(tl);
      }
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg, justifyContent: "center" }}>
        <ActivityIndicator color={colors.primary} />
      </SafeAreaView>
    );
  }
  if (!appdoc) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg, padding: 24 }}>
        <Txt variant="muted">Application not found.</Txt>
      </SafeAreaView>
    );
  }

  const currentIdx = STATUS_ORDER.indexOf(timeline?.current_status || appdoc.status);
  const isRejected = (timeline?.current_status || appdoc.status) === "rejected";

  return (
    <SafeAreaView style={styles.c} edges={["top"]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="chevron-back" size={28} color={colors.textPrimary} />
        </TouchableOpacity>
        <Txt variant="h3">Application</Txt>
        <View style={{ width: 28 }} />
      </View>

      <Screen noPad>
        <View style={{ padding: 20 }}>
          {/* Job summary */}
          <Card>
            <Txt variant="h2">{appdoc.job_title}</Txt>
            {job ? (
              <>
                <Txt variant="muted" style={{ marginTop: 4 }}>
                  {job.company || job.employer_name} · {job.location || "Anywhere"}
                </Txt>
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
                  <Tag text={(job.category || "fresher")} />
                  {job.experience_required ? <Tag text={`${job.experience_required}y+`} /> : null}
                  {(job.skills_required || []).slice(0, 3).map((s: string) => (
                    <Tag key={s} text={s} />
                  ))}
                </View>
              </>
            ) : null}
            <TouchableOpacity
              testID="view-job"
              style={{ marginTop: 12, alignSelf: "flex-start" }}
              onPress={() => router.push(`/student/jobs/${appdoc.job_id}`)}
            >
              <Txt style={{ color: colors.primary, fontWeight: "700" }}>View full job →</Txt>
            </TouchableOpacity>
          </Card>

          {/* Status timeline */}
          <Card style={{ marginTop: 16 }}>
            <Txt variant="h3">Status timeline</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginBottom: 12, marginTop: 2 }}>
              Date-wise progress (admin verified)
            </Txt>
            {STATUS_ORDER.map((s, i) => {
              const reached = !isRejected && i <= currentIdx;
              const active = i === currentIdx;
              const evt = (timeline?.history || []).find((h: any) => h.status === s);
              return (
                <View key={s} style={styles.step}>
                  <View style={styles.dotCol}>
                    <View style={[styles.dot, reached ? styles.dotOn : styles.dotOff, active ? styles.dotActive : null]}>
                      {reached ? <Ionicons name="checkmark" size={12} color="#fff" /> : null}
                    </View>
                    {i < STATUS_ORDER.length - 1 ? (
                      <View style={[styles.line, reached && i < currentIdx ? styles.lineOn : null]} />
                    ) : null}
                  </View>
                  <View style={{ flex: 1, paddingBottom: i < STATUS_ORDER.length - 1 ? 18 : 0 }}>
                    <Txt style={{ fontWeight: active ? "800" : "600", color: reached ? colors.textPrimary : colors.textSecondary, textTransform: "capitalize" }}>
                      {s.replace(/_/g, " ")}
                    </Txt>
                    {evt ? (
                      <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                        {new Date(evt.at).toLocaleString()}
                        {evt.note ? ` · ${evt.note}` : ""}
                      </Txt>
                    ) : null}
                  </View>
                </View>
              );
            })}
            {isRejected ? (
              <View style={[styles.step, { marginTop: 6 }]}>
                <View style={styles.dotCol}>
                  <View style={[styles.dot, { backgroundColor: colors.error }]}>
                    <Ionicons name="close" size={12} color="#fff" />
                  </View>
                </View>
                <Txt style={{ fontWeight: "800", color: colors.error, marginLeft: 4 }}>Rejected</Txt>
              </View>
            ) : null}
          </Card>

          {appdoc.referrer_pro_name ? (
            <Card style={{ marginTop: 12, backgroundColor: "#F3EEFF" }}>
              <Txt variant="label" style={{ color: "#7C3AED" }}>⭐ Referral</Txt>
              <Txt variant="h3" style={{ marginTop: 4 }}>Referred by {appdoc.referrer_pro_name}</Txt>
              {appdoc.note ? <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>&quot;{appdoc.note}&quot;</Txt> : null}
            </Card>
          ) : null}

          {timeline?.pending_changes?.length ? (
            <Card style={{ marginTop: 12, backgroundColor: "#FFF7E6" }}>
              <Txt variant="label" style={{ color: colors.warning }}>Pending admin review</Txt>
              {timeline.pending_changes.map((p: any) => (
                <View key={p.id} style={{ marginTop: 6 }}>
                  <Txt style={{ fontWeight: "600", textTransform: "capitalize" }}>
                    → {p.to_status.replace(/_/g, " ")}
                  </Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary }}>
                    by {p.requested_by_name} · {new Date(p.created_at).toLocaleString()}
                  </Txt>
                </View>
              ))}
            </Card>
          ) : null}
        </View>
      </Screen>
    </SafeAreaView>
  );
}

function Tag({ text }: { text: string }) {
  return (
    <View style={styles.tag}>
      <Txt variant="small" style={{ fontWeight: "600", textTransform: "capitalize" }}>{text}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.bg },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border },
  tag: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  step: { flexDirection: "row", alignItems: "flex-start" },
  dotCol: { width: 32, alignItems: "center" },
  dot: { width: 24, height: 24, borderRadius: 12, alignItems: "center", justifyContent: "center", marginTop: 2 },
  dotOn: { backgroundColor: colors.success },
  dotOff: { backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border },
  dotActive: { backgroundColor: colors.primary, transform: [{ scale: 1.1 }] },
  line: { width: 2, flex: 1, backgroundColor: colors.border, marginTop: 2 },
  lineOn: { backgroundColor: colors.success },
});
