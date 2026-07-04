import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, Alert, Share, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { successAlert } from "@/src/lib/successAlert";

export default function JobDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [job, setJob] = useState<any>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [j, savedList] = await Promise.all([
        api<any>(`/jobs/${id}`),
        api<any[]>(`/saved-jobs`).catch(() => []),
      ]);
      setJob(j);
      setSaved(savedList.some((x) => x.id === id));
    } catch (e: any) {
      Alert.alert("Failed to load job", e.message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function apply() {
    setBusy(true);
    try {
      const r = await api<{ used_free?: boolean }>("/jobs/apply", { method: "POST", body: { job_id: id } });
      successAlert.show({
        title: "Application Submitted",
        message: "Your job application has been submitted successfully.",
        onOk: () => router.back(),
      });
      load();
    } catch (e: any) {
      const msg = e.message || "";
      if (/insufficient credit/i.test(msg)) {
        Alert.alert(
          "Insufficient Credits",
          "You don't have enough credits to continue. Please purchase additional credits.",
          [
            { text: "Buy Credits", onPress: () => router.push("/student/wallet") },
            { text: "Cancel", style: "cancel" },
          ],
        );
      } else {
        Alert.alert("Cannot apply", msg);
      }
    } finally {
      setBusy(false);
    }
  }

  async function toggleSave() {
    try {
      if (saved) {
        await api(`/jobs/${id}/save`, { method: "DELETE" });
        setSaved(false);
      } else {
        await api(`/jobs/${id}/save`, { method: "POST" });
        setSaved(true);
      }
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    }
  }

  async function shareJob() {
    try {
      await Share.share({
        title: `${job?.title} @ ${job?.company || job?.employer_name}`,
        message: `Check out this role on ReferME:\n\n${job?.title} — ${job?.company || job?.employer_name}\n${job?.location || ""}\n\n${(job?.description || "").slice(0, 200)}…`,
      });
    } catch {}
  }

  if (loading) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg, justifyContent: "center" }}>
        <ActivityIndicator color={colors.primary} />
      </SafeAreaView>
    );
  }
  if (!job) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg, padding: 24 }}>
        <Txt variant="muted">Job not found.</Txt>
      </SafeAreaView>
    );
  }

  const openings = job.open_positions || job.bulk_openings || 1;
  return (
    <SafeAreaView style={styles.c} edges={["top"]}>
      <View style={styles.header}>
        <TouchableOpacity testID="back-btn" onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="chevron-back" size={28} color={colors.textPrimary} />
        </TouchableOpacity>
        <Txt variant="h3">Job details</Txt>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <TouchableOpacity testID="save-job" onPress={toggleSave} hitSlop={10}>
            <Ionicons name={saved ? "bookmark" : "bookmark-outline"} size={24} color={colors.primary} />
          </TouchableOpacity>
          <TouchableOpacity testID="share-job" onPress={shareJob} hitSlop={10}>
            <Ionicons name="share-social" size={24} color={colors.textPrimary} />
          </TouchableOpacity>
        </View>
      </View>

      <Screen noPad>
        <View style={{ padding: 20, paddingBottom: 80 }}>
          <Txt variant="h1">{job.title}</Txt>
          <Txt variant="muted" style={{ marginTop: 4 }}>{job.company || job.employer_name}</Txt>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
            {job.location ? <InfoChip icon="location" text={job.location} /> : null}
            <InfoChip icon="briefcase" text={(job.category || "fresher").toString()} />
            {job.experience_required ? <InfoChip icon="time" text={`${job.experience_required}y+`} /> : null}
            <InfoChip icon="people" text={`${openings} opening${openings > 1 ? "s" : ""}`} />
            {job.salary_range ? <InfoChip icon="cash" text={job.salary_range} /> : null}
          </View>

          {job.skills_required?.length ? (
            <Card style={{ marginTop: 16 }}>
              <Txt variant="label">Skill set</Txt>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                {job.skills_required.map((s: string) => (
                  <View key={s} style={styles.chip}><Txt variant="small" style={{ fontWeight: "600" }}>{s}</Txt></View>
                ))}
              </View>
            </Card>
          ) : null}

          <Card style={{ marginTop: 12 }}>
            <Txt variant="label">Description</Txt>
            <Txt style={{ marginTop: 6, lineHeight: 22 }}>{job.description}</Txt>
          </Card>

          <Card style={{ marginTop: 12 }}>
            <Row label="Posted by" value={job.posted_by_name || job.employer_name || "—"} />
            <Row label="Posted date" value={new Date(job.created_at).toLocaleDateString()} />
            {job.updated_at && job.updated_at !== job.created_at ? (
              <Row label="Updated" value={new Date(job.updated_at).toLocaleDateString()} />
            ) : null}
            <Row label="Status" value={(job.status || "open").toUpperCase()} />
            {job.applied ? (
              <Row label="Your application" value={(job.application_status || "applied").replace(/_/g, " ")} highlight />
            ) : null}
          </Card>
        </View>
      </Screen>

      {/* Sticky bottom action bar */}
      {!job.applied ? (
        <View style={styles.bottomBar}>
          <Button testID="apply-now" title="Apply now" loading={busy} onPress={apply} style={{ flex: 1 }} />
        </View>
      ) : (
        <View style={styles.bottomBar}>
          <View style={[styles.appliedPill, { flex: 1 }]}>
            <Ionicons name="checkmark-circle" size={20} color={colors.success} />
            <Txt style={{ color: colors.success, fontWeight: "700", marginLeft: 6, textTransform: "capitalize" }}>
              {(job.application_status || "applied").replace(/_/g, " ")}
            </Txt>
          </View>
        </View>
      )}
    </SafeAreaView>
  );
}

function InfoChip({ icon, text }: { icon: any; text: string }) {
  return (
    <View style={styles.infoChip}>
      <Ionicons name={icon} size={14} color={colors.textSecondary} />
      <Txt variant="small" style={{ marginLeft: 4, textTransform: "capitalize" }}>{text}</Txt>
    </View>
  );
}
function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <View style={{ flexDirection: "row", paddingVertical: 6, alignItems: "center" }}>
      <Txt variant="small" style={{ color: colors.textSecondary, width: 130 }}>{label}</Txt>
      <Txt style={{ fontWeight: highlight ? "700" : "500", color: highlight ? colors.primary : colors.textPrimary, textTransform: highlight ? "capitalize" : undefined }}>{value}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.bg },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border },
  chip: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  infoChip: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999 },
  bottomBar: { position: "absolute", left: 0, right: 0, bottom: 0, padding: 16, paddingBottom: 24, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, flexDirection: "row" },
  appliedPill: { flexDirection: "row", alignItems: "center", justifyContent: "center", backgroundColor: "#E6F9F0", padding: 14, borderRadius: 999 },
});
