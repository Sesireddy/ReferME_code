import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, Alert, Modal, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter, Stack } from "expo-router";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function JobApplicants() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [job, setJob] = useState<any>(null);
  const [apps, setApps] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const [referApp, setReferApp] = useState<any | null>(null);
  const [referNote, setReferNote] = useState("");
  const [hireApp, setHireApp] = useState<any | null>(null);
  const [hireNote, setHireNote] = useState("");
  const [proofB64, setProofB64] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const j = await api<any>(`/jobs/${id}`);
      setJob(j);
      const a = await api<any[]>(`/jobs/${id}/applicants`);
      setApps(a || []);
    } catch (e: any) {
      Alert.alert("Error", e.message);
    } finally {
      setRefreshing(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function doRefer() {
    if (!referApp) return;
    setSubmitting(true);
    try {
      await api(`/applications/refer-own`, {
        method: "POST",
        body: { application_id: referApp.id, note: referNote },
      });
      setReferApp(null);
      setReferNote("");
      Alert.alert("Referred ✅", "Status updated: Applied → Shortlisted → Referred");
      load();
    } catch (e: any) {
      Alert.alert("Error", e.message);
    } finally {
      setSubmitting(false);
    }
  }
  async function doHire() {
    if (!hireApp) return;
    if (!hireNote && !proofB64) {
      return Alert.alert("Evidence required", "Add a note or proof screenshot to submit for admin verification.");
    }
    setSubmitting(true);
    try {
      await api(`/applications/hire`, {
        method: "POST",
        body: {
          application_id: hireApp.id,
          note: hireNote,
          proof_base64: proofB64 || null,
        },
      });
      setHireApp(null);
      setHireNote("");
      setProofB64("");
      Alert.alert("Submitted ✅", "Hire is pending admin verification. +1500 credits will be added once approved.");
      load();
    } catch (e: any) {
      Alert.alert("Error", e.message);
    } finally {
      setSubmitting(false);
    }
  }

  function statusColor(s: string) {
    if (s === "hired") return { bg: "#E8F5E9", fg: "#2E7D32" };
    if (s === "hired_pending") return { bg: "#FFF3E0", fg: "#E65100" };
    if (s === "referred") return { bg: "#EDE7F6", fg: "#5E35B1" };
    if (s === "shortlisted") return { bg: "#E3F2FD", fg: "#1565C0" };
    if (s === "rejected") return { bg: "#FFEBEE", fg: "#C62828" };
    return { bg: colors.surfaceAlt, fg: colors.textSecondary };
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Stack.Screen options={{ title: job?.title || "Applicants" }} />
      <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 12 }}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </TouchableOpacity>
        <View style={{ flex: 1, marginLeft: 10 }}>
          <Txt variant="h2" numberOfLines={1}>{job?.title || "Job"}</Txt>
          <Txt variant="small" style={{ color: colors.textSecondary }}>
            {job?.company} · {apps.length} applicant{apps.length === 1 ? "" : "s"}
          </Txt>
        </View>
      </View>

      {apps.length === 0 ? (
        <Card style={{ alignItems: "center", paddingVertical: 30 }}>
          <Ionicons name="people-outline" size={42} color={colors.textSecondary} />
          <Txt variant="h3" style={{ marginTop: 10 }}>No applicants yet</Txt>
          <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4, textAlign: "center" }}>
            Share your job link to attract candidates.
          </Txt>
        </Card>
      ) : (
        apps.map((a: any) => {
          const sp = a.student_profile || {};
          const sc = statusColor(a.status || "");
          const canRefer = !["referred", "hired", "hired_pending"].includes(a.status || "");
          const canHire = !["hired", "hired_pending"].includes(a.status || "");
          return (
            <Card key={a.id} style={{ marginBottom: 10 }}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <View style={styles.avatar}>
                  <Txt style={{ color: "#fff", fontWeight: "700" }}>
                    {(sp.name || a.student_name || "?").slice(0, 1).toUpperCase()}
                  </Txt>
                </View>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Txt variant="h3" numberOfLines={1}>{sp.name || a.student_name}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary }}>
                    {sp.education || "—"} {sp.passed_out_year ? `'${String(sp.passed_out_year).slice(-2)}` : ""} · {sp.current_location || "—"}
                  </Txt>
                </View>
                <View style={[styles.pill, { backgroundColor: sc.bg }]}>
                  <Txt variant="small" style={{ color: sc.fg, fontWeight: "700" }}>
                    {(a.status || "").replace("_", " ")}
                  </Txt>
                </View>
              </View>

              {(sp.skills || []).length ? (
                <View style={{ flexDirection: "row", flexWrap: "wrap", marginTop: 8, gap: 6 }}>
                  {(sp.skills || []).slice(0, 6).map((s: string) => (
                    <View key={s} style={styles.skill}><Txt variant="small">{s}</Txt></View>
                  ))}
                </View>
              ) : null}

              <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 10 }}>
                <Txt variant="small" style={{ color: colors.textSecondary }}>
                  Resume score: {sp.resume_score ?? 0}/100
                </Txt>
                {sp.years_of_experience ? (
                  <Txt variant="small" style={{ color: colors.textSecondary }}>
                    {sp.years_of_experience}y exp
                  </Txt>
                ) : null}
              </View>

              <View style={styles.actionRow}>
                {canRefer ? (
                  <Button
                    testID={`refer-${a.id}`}
                    title="Refer"
                    onPress={() => { setReferApp(a); setReferNote(""); }}
                    style={{ flex: 1, height: 38 }}
                  />
                ) : null}
                {canHire ? (
                  <Button
                    testID={`hire-${a.id}`}
                    title={a.status === "referred" ? "Mark Hired" : "Hired"}
                    variant="secondary"
                    onPress={() => { setHireApp(a); setHireNote(""); setProofB64(""); }}
                    style={{ flex: 1, height: 38 }}
                  />
                ) : null}
              </View>
            </Card>
          );
        })
      )}

      {/* Refer modal */}
      <Modal visible={!!referApp} transparent animationType="slide" onRequestClose={() => setReferApp(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalSheet}>
            <Txt variant="h2" style={{ marginBottom: 4 }}>Refer candidate</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginBottom: 12 }}>
              {referApp?.student_name} for {job?.title}
            </Txt>
            <Input
              label="Note (optional)"
              placeholder="Why this candidate is a strong fit…"
              value={referNote}
              onChangeText={setReferNote}
              multiline
            />
            <Txt variant="small" style={{ color: colors.textSecondary, marginBottom: 12 }}>
              Status will move: Applied → Shortlisted → Referred by you.
            </Txt>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Button title="Cancel" variant="secondary" onPress={() => setReferApp(null)} style={{ flex: 1 }} />
              <Button testID="confirm-refer" title="Refer" onPress={doRefer} loading={submitting} style={{ flex: 1 }} />
            </View>
          </View>
        </View>
      </Modal>

      {/* Hire modal */}
      <Modal visible={!!hireApp} transparent animationType="slide" onRequestClose={() => setHireApp(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalSheet}>
            <Txt variant="h2" style={{ marginBottom: 4 }}>Mark as Hired</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginBottom: 12 }}>
              {hireApp?.student_name} for {job?.title}
            </Txt>
            <ScrollView>
              <Input
                label="Evidence note (offer letter ref / email subject)"
                placeholder="e.g. Offered SDE-1 on 12-Jun-2025 via HR portal"
                value={hireNote}
                onChangeText={setHireNote}
                multiline
              />
              <Input
                label="Proof screenshot (paste base64)"
                placeholder="data:image/png;base64,…"
                value={proofB64}
                onChangeText={setProofB64}
                multiline
              />
              <Txt variant="small" style={{ color: colors.textSecondary, marginBottom: 12 }}>
                ⚠️ Admin will verify before crediting +1500 to your wallet.
              </Txt>
            </ScrollView>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Button title="Cancel" variant="secondary" onPress={() => setHireApp(null)} style={{ flex: 1 }} />
              <Button testID="confirm-hire" title="Submit" onPress={doHire} loading={submitting} style={{ flex: 1 }} />
            </View>
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

const styles = StyleSheet.create({
  iconBtn: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: "#7C3AED", alignItems: "center", justifyContent: "center" },
  pill: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 },
  skill: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 },
  actionRow: { flexDirection: "row", gap: 8, marginTop: 12 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  modalSheet: { backgroundColor: colors.bg, padding: 20, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: "85%" },
});
