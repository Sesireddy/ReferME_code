import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, FlatList, Linking, Modal, Alert, Image } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { Picker } from "@/src/components/Picker";
import { ScreenTitle } from "@/src/components/ScreenTitle";
import { ExportMenu } from "@/src/components/ExportMenu";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { successAlert } from "@/src/lib/successAlert";

const STATUS_OPTS = [
  { value: "", label: "All" },
  { value: "available", label: "Available" },
  { value: "booked", label: "Booked" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

export default function AdminInterviews() {
  const [items, setItems] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [q, setQ] = useState("");
  const [candidate, setCandidate] = useState("");
  const [pro, setPro] = useState("");
  const [skill, setSkill] = useState("");
  const [date, setDate] = useState("");
  // Cancel booking modal
  const [cancelling, setCancelling] = useState<any | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelBusy, setCancelBusy] = useState(false);
  // Detail modal (rating + feedback + proof viewer)
  const [detail, setDetail] = useState<any | null>(null);
  // Full-screen proof viewer
  const [proofPreview, setProofPreview] = useState<string>("");

  async function submitCancel() {
    if (!cancelling) return;
    if (cancelReason.trim().length < 2) return Alert.alert("Reason required", "Please add a short reason for cancelling this booking.");
    setCancelBusy(true);
    try {
      const r = await api<any>(`/admin/interviews/slots/${cancelling.id}/cancel-booking`, {
        method: "POST",
        body: { reason: cancelReason.trim(), refund: true },
      });
      setCancelling(null);
      setCancelReason("");
      successAlert.show({
        title: "Booking Cancelled",
        message: `Slot released. Student refunded ${r.refund} credits and both parties notified.`,
      });
      load();
    } catch (e: any) {
      Alert.alert("Failed", e.message || "Could not cancel booking.");
    } finally {
      setCancelBusy(false);
    }
  }
  const [status, setStatus] = useState<string | null>("");

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.set("q", q.trim());
      if (candidate.trim()) params.set("candidate", candidate.trim());
      if (pro.trim()) params.set("pro", pro.trim());
      if (skill.trim()) params.set("skill", skill.trim());
      if (date) params.set("date", date);
      if (status) params.set("status", status);
      const data = await api<any[]>(`/admin/interviews/search${params.toString() ? "?" + params.toString() : ""}`);
      setItems(data);
    } catch {}
    setRefreshing(false);
  }, [q, candidate, pro, skill, date, status]);

  useEffect(() => { load(); }, []);

  function reset() {
    setQ(""); setCandidate(""); setPro(""); setSkill(""); setDate(""); setStatus("");
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <ScreenTitle title="Interviews" icon="mic" color={colors.primary} />
        </View>
        <ExportMenu entity="interviews" label="Export Interviews" />
        <View style={{ width: 8 }} />
        <TouchableOpacity onPress={() => setShowFilters(p => !p)} style={styles.btn}>
          <Ionicons name="options" size={20} color={colors.textPrimary} />
        </TouchableOpacity>
      </View>
      <Input value={q} onChangeText={setQ} placeholder="Search by ID / candidate / pro / meeting URL" style={{ marginTop: 8 }} />

      {showFilters ? (
        <Card style={{ marginTop: 8 }}>
          <Input label="Candidate Name" value={candidate} onChangeText={setCandidate} />
          <Input label="Professional Name" value={pro} onChangeText={setPro} />
          <Input label="Skill Set" value={skill} onChangeText={setSkill} placeholder="e.g. Java" />
          <Input label="Date (YYYY-MM-DD)" value={date} onChangeText={setDate} />
          <Picker label="Status" options={STATUS_OPTS} value={status} onChange={(v) => setStatus(v as string)} placeholder="All" />
          <View style={{ flexDirection: "row", gap: 10, marginTop: 4 }}>
            <Button title="Apply Filter" onPress={() => { load(); setShowFilters(false); }} style={{ flex: 1 }} />
            <Button title="Reset" variant="outline" onPress={() => { reset(); load(); }} style={{ flex: 1 }} />
          </View>
        </Card>
      ) : null}

      <Txt variant="small" style={{ marginTop: 12, color: colors.textSecondary }}>{items.length} result(s)</Txt>
      <FlatList
        data={items}
        keyExtractor={(x) => x.id}
        scrollEnabled={false}
        renderItem={({ item: s }) => {
          const isCompleted = s.status === "completed";
          const creditsAwarded = isCompleted ? 35 : 0;
          const hasProof = !!s.proof_screenshot;
          const isPdf = hasProof && String(s.proof_screenshot).startsWith("data:application/pdf");
          return (
            <Card style={{ marginTop: 10 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <View style={{ flex: 1 }}>
                  <Txt variant="h3" numberOfLines={1}>{s.student_name || "—"} ↔ {s.pro_name || "—"}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                    {(s.skill_set || []).join(", ") || "—"}
                  </Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                    📅 {new Date(s.start_at).toLocaleString()}
                  </Txt>
                  {s.meeting_url ? (
                    <TouchableOpacity onPress={() => Linking.openURL(s.meeting_url)} hitSlop={6} style={{ marginTop: 4 }}>
                      <Txt variant="small" style={{ color: colors.primary }} numberOfLines={1}>{s.meeting_url}</Txt>
                    </TouchableOpacity>
                  ) : null}
                </View>
                <View style={[styles.statusPill, { backgroundColor: pillColor(s.status) }]}>
                  <Txt style={{ color: "#fff", fontWeight: "700", fontSize: 11, textTransform: "capitalize" }}>{s.status}</Txt>
                </View>
              </View>

              {/* Completion details: rating + credits + feedback preview + proof thumb */}
              {isCompleted ? (
                <View style={styles.completionBox}>
                  <View style={styles.completionRow}>
                    <View style={styles.miniChip}>
                      <Ionicons name="star" size={13} color="#F59E0B" />
                      <Txt style={[styles.miniChipText, { color: "#F59E0B" }]}>
                        {s.candidate_rating != null ? `${s.candidate_rating}/10` : "—"}
                      </Txt>
                    </View>
                    <View style={[styles.miniChip, { backgroundColor: "#F0FDF4" }]}>
                      <Ionicons name="cash" size={13} color={colors.success} />
                      <Txt style={[styles.miniChipText, { color: colors.success }]}>+{creditsAwarded} credits</Txt>
                    </View>
                    {hasProof ? (
                      <View style={[styles.miniChip, { backgroundColor: "#F5F3FF" }]}>
                        <Ionicons name="shield-checkmark" size={13} color="#7C3AED" />
                        <Txt style={[styles.miniChipText, { color: "#7C3AED" }]}>Proof attached</Txt>
                      </View>
                    ) : (
                      <View style={[styles.miniChip, { backgroundColor: "#FEE2E2" }]}>
                        <Ionicons name="alert-circle" size={13} color={colors.error} />
                        <Txt style={[styles.miniChipText, { color: colors.error }]}>No proof</Txt>
                      </View>
                    )}
                  </View>

                  {s.candidate_feedback ? (
                    <View style={{ marginTop: 8 }}>
                      <Txt variant="small" style={{ color: colors.textSecondary, marginBottom: 2 }}>Feedback</Txt>
                      <Txt numberOfLines={2} style={{ color: colors.textPrimary }}>
                        {s.candidate_feedback}
                      </Txt>
                    </View>
                  ) : null}

                  {hasProof ? (
                    <View style={styles.proofRow}>
                      {isPdf ? (
                        <View style={[styles.proofThumb, { alignItems: "center", justifyContent: "center" }]}>
                          <Ionicons name="document-text" size={26} color="#7C3AED" />
                          <Txt variant="small" style={{ marginTop: 4, color: colors.textSecondary }}>PDF</Txt>
                        </View>
                      ) : (
                        <Image source={{ uri: s.proof_screenshot }} style={styles.proofThumb} resizeMode="cover" />
                      )}
                      <TouchableOpacity
                        testID={`view-proof-${s.id}`}
                        onPress={() => isPdf ? Linking.openURL(s.proof_screenshot).catch(() => {}) : setProofPreview(s.proof_screenshot)}
                        style={styles.viewProofBtn}
                      >
                        <Ionicons name="eye" size={14} color="#fff" />
                        <Txt style={styles.viewProofText}>View Full Proof</Txt>
                      </TouchableOpacity>
                    </View>
                  ) : null}

                  <TouchableOpacity testID={`detail-${s.id}`} onPress={() => setDetail(s)} style={styles.detailBtn}>
                    <Ionicons name="information-circle" size={14} color={colors.primary} />
                    <Txt style={styles.detailBtnText}>View full details</Txt>
                  </TouchableOpacity>
                </View>
              ) : null}

              {s.status === "booked" ? (
                <Button
                  testID={`cancel-booking-${s.id}`}
                  title="Cancel Booking & Refund 49 credits"
                  variant="outline"
                  onPress={() => { setCancelling(s); setCancelReason(""); }}
                  icon={<Ionicons name="close-circle" size={16} color={colors.error} />}
                  style={{ marginTop: 10 }}
                />
              ) : null}
            </Card>
          );
        }}
        ListEmptyComponent={<Txt variant="muted" style={{ marginTop: 16 }}>No interview slots found.</Txt>}
      />

      {/* Cancel Booking Modal */}
      <Modal visible={!!cancelling} transparent animationType="slide" onRequestClose={() => setCancelling(null)}>
        <View style={modStyles.modalBg}>
          <View style={modStyles.modalCard}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Txt variant="h3">Cancel Booking</Txt>
              <TouchableOpacity onPress={() => setCancelling(null)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.textPrimary} />
              </TouchableOpacity>
            </View>
            {cancelling ? (
              <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>
                {cancelling.student_name} ↔ {cancelling.pro_name} · {new Date(cancelling.start_at).toLocaleString()}
              </Txt>
            ) : null}
            <Input
              testID="cancel-reason"
              label="Reason (required)"
              placeholder="e.g. Slot mismatch / Compliance / User request"
              value={cancelReason}
              onChangeText={setCancelReason}
              multiline
              numberOfLines={3}
            />
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 6 }}>
              💡 The slot will be released, the student will be auto-refunded 49 credits, and both parties will be notified.
            </Txt>
            <Button
              testID="cancel-submit"
              title="Cancel Booking & Refund"
              variant="outline"
              loading={cancelBusy}
              onPress={submitCancel}
              icon={<Ionicons name="close-circle" size={18} color={colors.error} />}
              style={{ marginTop: 12 }}
            />
          </View>
        </View>
      </Modal>
      {/* Full-screen proof viewer */}
      <Modal visible={!!proofPreview} transparent animationType="fade" onRequestClose={() => setProofPreview("")}>
        <TouchableOpacity activeOpacity={1} onPress={() => setProofPreview("")} style={modStyles.lightboxBg}>
          {proofPreview ? (
            <Image source={{ uri: proofPreview }} style={modStyles.lightboxImg} resizeMode="contain" />
          ) : null}
          <View style={modStyles.lightboxClose}>
            <Ionicons name="close" size={26} color="#fff" />
          </View>
        </TouchableOpacity>
      </Modal>

      {/* Interview detail modal */}
      <Modal visible={!!detail} transparent animationType="slide" onRequestClose={() => setDetail(null)}>
        <View style={modStyles.modalBg}>
          <View style={modStyles.modalCard}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Txt variant="h3">Interview Details</Txt>
              <TouchableOpacity onPress={() => setDetail(null)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.textPrimary} />
              </TouchableOpacity>
            </View>
            {detail ? (
              <View style={{ marginTop: 10, gap: 6 }}>
                <Row label="Candidate" value={detail.student_name || "—"} />
                <Row label="Professional" value={detail.pro_name || "—"} />
                <Row label="Skills" value={(detail.skill_set || []).join(", ") || "—"} />
                <Row label="Scheduled" value={new Date(detail.start_at).toLocaleString()} />
                <Row label="Status" value={String(detail.status || "—").toUpperCase()} />
                <Row label="Overall Rating" value={detail.candidate_rating != null ? `${detail.candidate_rating}/10` : "—"} />
                <Row label="Credits Awarded" value={detail.status === "completed" ? "+35" : "0"} />
                {detail.candidate_feedback ? (
                  <View style={{ marginTop: 6 }}>
                    <Txt variant="small" style={{ color: colors.textSecondary }}>Feedback</Txt>
                    <Txt style={{ color: colors.textPrimary, marginTop: 2 }}>{detail.candidate_feedback}</Txt>
                  </View>
                ) : null}
              </View>
            ) : null}
            <Button title="Close" variant="outline" onPress={() => setDetail(null)} style={{ marginTop: 14 }} />
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
      <Txt variant="small" style={{ color: colors.textSecondary }}>{label}</Txt>
      <Txt style={{ fontWeight: "700", flexShrink: 1, textAlign: "right", marginLeft: 12 }}>{value}</Txt>
    </View>
  );
}

const modStyles = StyleSheet.create({
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.bg, padding: 18, borderTopLeftRadius: 20, borderTopRightRadius: 20 },
  lightboxBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.95)", alignItems: "center", justifyContent: "center" },
  lightboxImg: { width: "100%", height: "85%" },
  lightboxClose: { position: "absolute", top: 40, right: 20, width: 44, height: 44, borderRadius: 22, backgroundColor: "rgba(255,255,255,0.2)", alignItems: "center", justifyContent: "center" },
});

function pillColor(s: string) {
  if (s === "available") return colors.success;
  if (s === "booked") return colors.warning;
  if (s === "completed") return "#7C3AED";
  if (s === "cancelled") return colors.error;
  return colors.textSecondary;
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  btn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  statusPill: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 12, alignSelf: "flex-start" },
  completionBox: { marginTop: 10, padding: 10, borderRadius: 12, backgroundColor: colors.surfaceAlt },
  completionRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  miniChip: { flexDirection: "row", alignItems: "center", paddingHorizontal: 8, paddingVertical: 4, borderRadius: 10, backgroundColor: "#FFFBEB", gap: 4 },
  miniChipText: { fontSize: 11, fontWeight: "800" },
  proofRow: { marginTop: 10, flexDirection: "row", alignItems: "center", gap: 10 },
  proofThumb: { width: 70, height: 70, borderRadius: 8, backgroundColor: "#fff" },
  viewProofBtn: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: "#7C3AED", gap: 6 },
  viewProofText: { color: "#fff", fontWeight: "700", fontSize: 12 },
  detailBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", marginTop: 10, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: colors.primary + "55", gap: 6 },
  detailBtnText: { color: colors.primary, fontWeight: "700", fontSize: 12 },
});
