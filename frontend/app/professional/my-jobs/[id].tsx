import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, Alert, Modal, ScrollView, Image } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter, Stack } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system/legacy";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { successAlert } from "@/src/lib/successAlert";

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
  const [proofB64, setProofB64] = useState(""); // data URL of image/PDF
  const [proofPreview, setProofPreview] = useState(""); // image preview URI (empty for PDF)
  const [proofKind, setProofKind] = useState<"image" | "pdf" | "">("");
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
      successAlert.show({ title: "Candidate Referred", message: "Status updated: Applied → Shortlisted → Referred." });
      load();
    } catch (e: any) {
      Alert.alert("Error", e.message);
    } finally {
      setSubmitting(false);
    }
  }
  async function pickProofImage() {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        return Alert.alert("Permission required", "Please allow photo library access to upload proof.");
      }
      const res = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: false,
        quality: 0.75,
        base64: true,
      });
      if (res.canceled || !res.assets?.length) return;
      const a = res.assets[0];
      const mime = a.mimeType || "image/jpeg";
      const dataUrl = `data:${mime};base64,${a.base64}`;
      setProofB64(dataUrl);
      setProofPreview(a.uri);
      setProofKind("image");
    } catch (e: any) {
      Alert.alert("Could not pick image", String(e?.message || e));
    }
  }

  async function pickProofPdf() {
    try {
      const res = await DocumentPicker.getDocumentAsync({ type: ["application/pdf", "image/*"], copyToCacheDirectory: true });
      if (res.canceled || !res.assets?.length) return;
      const a = res.assets[0];
      const base64 = await FileSystem.readAsStringAsync(a.uri, { encoding: FileSystem.EncodingType.Base64 });
      const mime = a.mimeType || (a.name?.endsWith(".pdf") ? "application/pdf" : "image/jpeg");
      const dataUrl = `data:${mime};base64,${base64}`;
      setProofB64(dataUrl);
      setProofPreview(mime.startsWith("image/") ? a.uri : "");
      setProofKind(mime === "application/pdf" ? "pdf" : "image");
    } catch (e: any) {
      Alert.alert("Could not pick file", String(e?.message || e));
    }
  }

  async function doHire() {
    if (!hireApp) return;
    if (!hireNote && !proofB64) {
      return Alert.alert("Evidence required", "Add a note or proof attachment to submit for admin verification.");
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
      setProofPreview("");
      setProofKind("");
      successAlert.show({ title: "Hire Submitted", message: "Hire is pending admin verification. +1500 credits will be added once approved." });
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
      <Modal visible={!!hireApp} transparent animationType="slide" onRequestClose={() => { setHireApp(null); setHireNote(""); setProofB64(""); setProofPreview(""); setProofKind(""); }}>
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

              <Txt variant="label" style={{ marginTop: 8, marginBottom: 6 }}>Proof attachment <Txt style={{ color: colors.textSecondary, fontWeight: "400" }}>(image or PDF)</Txt></Txt>
              <Txt variant="small" style={{ color: colors.textSecondary, marginBottom: 6 }}>
                Upload the offer letter or hiring confirmation screenshot (JPG, PNG, PDF).
              </Txt>
              {proofB64 ? (
                <View style={styles.proofBox}>
                  {proofKind === "image" && proofPreview ? (
                    <Image source={{ uri: proofPreview }} style={styles.proofImg} resizeMode="cover" />
                  ) : (
                    <View style={[styles.proofImg, { alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceAlt }]}>
                      <Ionicons name="document-text" size={36} color={colors.primary} />
                      <Txt variant="small" style={{ marginTop: 4 }}>PDF uploaded</Txt>
                    </View>
                  )}
                  <TouchableOpacity testID="remove-hire-proof" onPress={() => { setProofB64(""); setProofPreview(""); setProofKind(""); }} style={styles.proofRemove}>
                    <Ionicons name="close" size={18} color="#fff" />
                  </TouchableOpacity>
                </View>
              ) : (
                <View style={{ flexDirection: "row", gap: 8, marginBottom: 8 }}>
                  <TouchableOpacity testID="pick-hire-image" onPress={pickProofImage} style={[styles.uploadBtn, { backgroundColor: "#7C3AED" + "12", borderColor: "#7C3AED" }]}>
                    <Ionicons name="image" size={18} color="#7C3AED" />
                    <Txt style={{ color: "#7C3AED", fontWeight: "700", marginLeft: 6 }}>Image</Txt>
                  </TouchableOpacity>
                  <TouchableOpacity testID="pick-hire-pdf" onPress={pickProofPdf} style={[styles.uploadBtn, { backgroundColor: colors.primary + "12", borderColor: colors.primary }]}>
                    <Ionicons name="document-attach" size={18} color={colors.primary} />
                    <Txt style={{ color: colors.primary, fontWeight: "700", marginLeft: 6 }}>PDF / File</Txt>
                  </TouchableOpacity>
                </View>
              )}

              <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 6, marginBottom: 12 }}>
                ⚠️ Admin will verify before crediting +1500 to your wallet.
              </Txt>
            </ScrollView>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Button title="Cancel" variant="secondary" onPress={() => { setHireApp(null); setHireNote(""); setProofB64(""); setProofPreview(""); setProofKind(""); }} style={{ flex: 1 }} />
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
  uploadBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", paddingVertical: 12, borderRadius: radius.lg, borderWidth: 1 },
  proofBox: { position: "relative", marginBottom: 8 },
  proofImg: { width: "100%", height: 160, borderRadius: radius.lg, backgroundColor: colors.surfaceAlt },
  proofRemove: { position: "absolute", top: 8, right: 8, width: 28, height: 28, borderRadius: 14, backgroundColor: "rgba(0,0,0,0.6)", alignItems: "center", justifyContent: "center" },
});
