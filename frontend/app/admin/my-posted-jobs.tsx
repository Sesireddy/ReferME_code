// Admin — My Posted Jobs. Lists every admin-authored job (drafts + published).
// Each card supports quick Publish (drafts) / Edit / Delete actions.
import React, { useCallback, useState } from "react";
import { View, StyleSheet, TouchableOpacity, RefreshControl, FlatList, Alert } from "react-native";
import { Stack, useRouter, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { successAlert } from "@/src/lib/successAlert";
import { webSafeAlert } from "@/src/lib/webSafeAlert";

type Job = {
  id: string;
  title: string;
  company: string;
  status: "draft" | "open" | "closed";
  location?: string;
  walk_in_date?: string;
  open_positions?: number;
  created_at?: string;
  updated_at?: string;
};

function badgeFor(status: string) {
  if (status === "draft") return { text: "Draft", bg: "#E5E7EB", color: "#374151" };
  if (status === "closed") return { text: "Closed", bg: "#FEE2E2", color: "#B91C1C" };
  return { text: "Live", bg: "#DCFCE7", color: "#166534" };
}

export default function AdminMyPostedJobs() {
  const router = useRouter();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [busy, setBusy] = useState(false);
  const [rowBusy, setRowBusy] = useState<string>("");

  const load = useCallback(async () => {
    setBusy(true);
    try { setJobs((await api<Job[]>("/admin/jobs/mine")) || []); }
    finally { setBusy(false); }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  async function publishDraft(id: string) {
    setRowBusy(id);
    try {
      await api(`/admin/jobs/${id}/publish`, { method: "POST", body: {} });
      successAlert.show({ title: "Published 🎉", message: "This job is now visible under Walk-in & Direct Jobs." });
      await load();
    } catch (e: any) { Alert.alert("Error", e?.message || "Failed to publish."); }
    finally { setRowBusy(""); }
  }

  function confirmDelete(job: Job) {
    const proceed = async () => {
      setRowBusy(job.id);
      try {
        await api(`/admin/jobs/${job.id}`, { method: "DELETE" });
        setJobs((p) => p.filter((x) => x.id !== job.id));
        successAlert.show({ title: "Deleted", message: `"${job.title}" has been removed.` });
      } catch (e: any) { Alert.alert("Error", e?.message || "Failed to delete."); }
      finally { setRowBusy(""); }
    };
    if (typeof window !== "undefined" && typeof (window as any).confirm === "function") {
      if ((window as any).confirm(`Delete "${job.title}"? This cannot be undone.`)) proceed();
    } else {
      Alert.alert("Delete Job", `Remove "${job.title}"?\nThis cannot be undone.`, [
        { text: "Cancel", style: "cancel" },
        { text: "Delete", style: "destructive", onPress: proceed },
      ]);
    }
  }

  const renderItem = ({ item: j }: { item: Job }) => {
    const b = badgeFor(j.status);
    const isBusy = rowBusy === j.id;
    return (
      <Card style={{ marginBottom: 12 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
          <View style={{ flex: 1 }}>
            <Txt variant="label" style={{ color: colors.textSecondary }}>{j.company}</Txt>
            <Txt variant="h3" style={{ marginTop: 2 }}>{j.title}</Txt>
          </View>
          <View style={[styles.badge, { backgroundColor: b.bg }]}>
            <Txt style={{ color: b.color, fontWeight: "800", fontSize: 11 }}>{b.text}</Txt>
          </View>
        </View>
        <View style={styles.metaRow}>
          <Ionicons name="location" size={13} color={colors.textSecondary} />
          <Txt variant="small" style={styles.metaText}>{j.location || "—"}</Txt>
          {j.open_positions ? (<><Ionicons name="people" size={13} color={colors.textSecondary} style={{ marginLeft: 10 }} /><Txt variant="small" style={styles.metaText}>{j.open_positions} positions</Txt></>) : null}
        </View>

        <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
          {j.status === "draft" ? (
            <Button testID={`publish-${j.id}`} title="Publish" onPress={() => publishDraft(j.id)} loading={isBusy} style={{ flex: 1 }} />
          ) : null}
          <TouchableOpacity testID={`edit-${j.id}`} onPress={() => router.push({ pathname: "/admin/post-job", params: { editId: j.id } })} style={[styles.iconBtn, { backgroundColor: colors.primary + "18" }]}>
            <Ionicons name="create" size={16} color={colors.primary} />
            <Txt style={{ color: colors.primary, fontWeight: "700", marginLeft: 6 }}>Edit</Txt>
          </TouchableOpacity>
          <TouchableOpacity testID={`delete-${j.id}`} onPress={() => confirmDelete(j)} style={[styles.iconBtn, { backgroundColor: colors.error + "18" }]} disabled={isBusy}>
            <Ionicons name="trash" size={16} color={colors.error} />
            <Txt style={{ color: colors.error, fontWeight: "700", marginLeft: 6 }}>Delete</Txt>
          </TouchableOpacity>
        </View>
      </Card>
    );
  };

  return (
    <Screen>
      <Stack.Screen options={{ title: "My Posted Jobs" }} />
      <FlatList
        data={jobs}
        keyExtractor={(j) => j.id}
        renderItem={renderItem}
        contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={busy} onRefresh={load} />}
        ListHeaderComponent={
          <View style={{ marginBottom: 12, flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <View style={{ flex: 1 }}>
              <Txt variant="h1">My Posted Jobs</Txt>
              <Txt variant="muted" style={{ marginTop: 2 }}>Drafts & Live openings you have published.</Txt>
            </View>
            <TouchableOpacity onPress={() => router.push("/admin/post-job")} style={styles.newBtn} testID="new-job-btn">
              <Ionicons name="add" size={18} color="#fff" />
              <Txt style={{ color: "#fff", fontWeight: "700", marginLeft: 4 }}>New</Txt>
            </TouchableOpacity>
          </View>
        }
        ListEmptyComponent={
          !busy ? (
            <View style={{ padding: 24, alignItems: "center" }}>
              <Ionicons name="briefcase-outline" size={48} color={colors.textSecondary} />
              <Txt variant="muted" style={{ marginTop: 12, textAlign: "center" }}>
                No jobs posted yet. Tap “New” above to publish your first Walk-in / Direct hire opening.
              </Txt>
            </View>
          ) : null
        }
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  metaRow: { flexDirection: "row", alignItems: "center", marginTop: 6 },
  metaText: { marginLeft: 4, color: colors.textSecondary },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.sm },
  iconBtn: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingVertical: 10, borderRadius: radius.md },
  newBtn: { flexDirection: "row", alignItems: "center", backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.md },
});
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const _webSafeAlert = webSafeAlert;
