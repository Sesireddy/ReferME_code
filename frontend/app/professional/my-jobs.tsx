import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, Alert, Modal, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function ProMyJobs() {
  const router = useRouter();
  const [jobs, setJobs] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [editing, setEditing] = useState<any | null>(null);
  const [editForm, setEditForm] = useState<any>({});

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await api<any[]>("/jobs/?mine=true");
      setJobs(r || []);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function close(jobId: string) {
    try {
      await api(`/jobs/${jobId}/close`, { method: "POST" });
      load();
    } catch (e: any) { Alert.alert("Error", e.message); }
  }
  async function reopen(jobId: string) {
    try {
      await api(`/jobs/${jobId}/reopen`, { method: "POST" });
      load();
    } catch (e: any) { Alert.alert("Error", e.message); }
  }

  function openEdit(job: any) {
    setEditing(job);
    setEditForm({
      title: job.title,
      company: job.company,
      location: job.location || "",
      salary_range: job.salary_range || "",
      description: job.description || "",
      open_positions: String(job.open_positions || 1),
      skills_required: (job.skills_required || []).join(", "),
    });
  }
  async function saveEdit() {
    if (!editing) return;
    try {
      await api(`/jobs/${editing.id}`, {
        method: "PATCH",
        body: {
          title: editForm.title,
          company: editForm.company,
          location: editForm.location,
          salary_range: editForm.salary_range,
          description: editForm.description,
          open_positions: parseInt(editForm.open_positions, 10) || 1,
          skills_required: editForm.skills_required.split(",").map((s: string) => s.trim()).filter(Boolean),
        },
      });
      setEditing(null);
      load();
    } catch (e: any) {
      Alert.alert("Error", e.message);
    }
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={styles.header}>
        <Txt variant="h1">My Posted Jobs</Txt>
        <TouchableOpacity testID="post-new" onPress={() => router.push("/professional/post-job")}>
          <View style={styles.addBtn}>
            <Ionicons name="add" size={22} color="#fff" />
          </View>
        </TouchableOpacity>
      </View>

      {jobs.length === 0 ? (
        <Card style={{ marginTop: 16, alignItems: "center", paddingVertical: 30 }}>
          <Ionicons name="briefcase-outline" size={42} color={colors.textSecondary} />
          <Txt variant="h3" style={{ marginTop: 10 }}>No jobs posted yet</Txt>
          <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4, textAlign: "center" }}>
            Post your first job and get +100 credits after 4 valid applications.
          </Txt>
          <Button testID="empty-post" title="Post a Job" onPress={() => router.push("/professional/post-job")} style={{ marginTop: 14, paddingHorizontal: 32 }} />
        </Card>
      ) : (
        jobs.map((j) => {
          const posted = j.created_at ? new Date(j.created_at) : null;
          const isOpen = j.status === "open";
          return (
            <Card key={j.id} style={{ marginTop: 12 }}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <View style={{ flex: 1 }}>
                  <Txt variant="h3" numberOfLines={1}>{j.title}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                    {j.company} · {j.location || "Remote"}
                  </Txt>
                </View>
                <View style={[styles.pill, { backgroundColor: isOpen ? "#E8F5E9" : "#FFEBEE" }]}>
                  <Txt variant="small" style={{ color: isOpen ? "#2E7D32" : "#C62828", fontWeight: "700" }}>
                    {(j.status || "").toUpperCase()}
                  </Txt>
                </View>
              </View>

              <View style={styles.metaRow}>
                <View style={styles.meta}>
                  <Ionicons name="layers" size={14} color={colors.textSecondary} />
                  <Txt variant="small" style={{ color: colors.textSecondary, marginLeft: 4 }}>{j.category}</Txt>
                </View>
                <View style={styles.meta}>
                  <Ionicons name="people" size={14} color={colors.textSecondary} />
                  <Txt variant="small" style={{ color: colors.textSecondary, marginLeft: 4 }}>
                    {j.applications_count ?? 0} applicant{(j.applications_count || 0) === 1 ? "" : "s"}
                  </Txt>
                </View>
                {posted ? (
                  <View style={styles.meta}>
                    <Ionicons name="calendar" size={14} color={colors.textSecondary} />
                    <Txt variant="small" style={{ color: colors.textSecondary, marginLeft: 4 }}>
                      {posted.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}
                    </Txt>
                  </View>
                ) : null}
                {j.posting_reward_paid ? (
                  <View style={[styles.meta, { backgroundColor: "#FFF4E0", borderRadius: 8, paddingHorizontal: 8, paddingVertical: 2 }]}>
                    <Ionicons name="gift" size={12} color="#FF8F00" />
                    <Txt variant="small" style={{ color: "#FF8F00", marginLeft: 4, fontWeight: "700" }}>+100 earned</Txt>
                  </View>
                ) : null}
              </View>

              <View style={styles.actionRow}>
                <Button
                  testID={`applicants-${j.id}`}
                  title="View Applicants"
                  onPress={() => router.push(`/professional/my-jobs/${j.id}`)}
                  style={{ flex: 1, height: 38 }}
                />
                <Button
                  testID={`edit-${j.id}`}
                  title="Edit"
                  variant="secondary"
                  onPress={() => openEdit(j)}
                  style={{ height: 38, paddingHorizontal: 14 }}
                />
                {isOpen ? (
                  <Button
                    testID={`close-${j.id}`}
                    title="Close"
                    variant="secondary"
                    onPress={() => close(j.id)}
                    style={{ height: 38, paddingHorizontal: 14 }}
                  />
                ) : (
                  <Button
                    testID={`reopen-${j.id}`}
                    title="Reopen"
                    variant="secondary"
                    onPress={() => reopen(j.id)}
                    style={{ height: 38, paddingHorizontal: 14 }}
                  />
                )}
              </View>
            </Card>
          );
        })
      )}

      <Modal visible={!!editing} transparent animationType="slide" onRequestClose={() => setEditing(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalSheet}>
            <Txt variant="h2" style={{ marginBottom: 12 }}>Edit job</Txt>
            <ScrollView>
              <Input label="Title" value={editForm.title} onChangeText={(v: string) => setEditForm({ ...editForm, title: v })} />
              <Input label="Company" value={editForm.company} onChangeText={(v: string) => setEditForm({ ...editForm, company: v })} />
              <Input label="Location" value={editForm.location} onChangeText={(v: string) => setEditForm({ ...editForm, location: v })} />
              <Input label="Salary range" value={editForm.salary_range} onChangeText={(v: string) => setEditForm({ ...editForm, salary_range: v })} />
              <Input label="Open positions" value={editForm.open_positions} onChangeText={(v: string) => setEditForm({ ...editForm, open_positions: v })} keyboardType="number-pad" />
              <Input label="Skills (comma-separated)" value={editForm.skills_required} onChangeText={(v: string) => setEditForm({ ...editForm, skills_required: v })} />
              <Input label="Description" value={editForm.description} onChangeText={(v: string) => setEditForm({ ...editForm, description: v })} multiline />
            </ScrollView>
            <View style={{ flexDirection: "row", gap: 8, marginTop: 8 }}>
              <Button title="Cancel" variant="secondary" onPress={() => setEditing(null)} style={{ flex: 1 }} />
              <Button testID="save-edit" title="Save" onPress={saveEdit} style={{ flex: 1 }} />
            </View>
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  addBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: "#7C3AED", alignItems: "center", justifyContent: "center" },
  pill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  metaRow: { flexDirection: "row", flexWrap: "wrap", gap: 14, marginTop: 10 },
  meta: { flexDirection: "row", alignItems: "center" },
  actionRow: { flexDirection: "row", gap: 8, marginTop: 14 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  modalSheet: { backgroundColor: colors.bg, padding: 20, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: "85%" },
});
