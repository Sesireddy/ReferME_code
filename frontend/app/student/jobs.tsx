import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, Alert, Modal, ScrollView } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

type Tab = "jobs" | "interview" | "applications";

export default function StudentJobs() {
  const params = useLocalSearchParams<{ tab?: string }>();
  const [tab, setTab] = useState<Tab>((params.tab as Tab) || "jobs");
  const [jobs, setJobs] = useState<any[]>([]);
  const [pros, setPros] = useState<any[]>([]);
  const [slots, setSlots] = useState<any[]>([]);
  const [selectedPro, setSelectedPro] = useState<any | null>(null);
  const [apps, setApps] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [j, p, a] = await Promise.all([
        api<any[]>("/jobs"),
        api<any[]>("/professionals"),
        api<any[]>("/applications"),
      ]);
      setJobs(j);
      setPros(p);
      setApps(a);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function apply(jobId: string) {
    try {
      const r = await api<{ used_free?: boolean }>("/jobs/apply", { method: "POST", body: { job_id: jobId } });
      Alert.alert("Applied", r.used_free ? "Used a free token!" : "49 credits spent.");
      load();
    } catch (e: any) {
      Alert.alert("Cannot apply", e.message);
    }
  }

  async function openPro(pro: any) {
    setSelectedPro(pro);
    try {
      const s = await api<any[]>(`/interviews/slots?pro_id=${pro.id}`);
      setSlots(s.filter((x) => x.status === "available"));
    } catch {
      setSlots([]);
    }
  }

  async function bookSlot(slotId: string) {
    try {
      const r = await api<{ used_free?: boolean }>("/interviews/book", { method: "POST", body: { slot_id: slotId } });
      Alert.alert("Booked", r.used_free ? "Used a free token!" : "49 credits spent.");
      setSelectedPro(null);
      load();
    } catch (e: any) {
      Alert.alert("Cannot book", e.message);
    }
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Txt variant="h1">Explore</Txt>
      <View style={styles.tabs}>
        {(["jobs", "interview", "applications"] as Tab[]).map((t) => (
          <TouchableOpacity
            key={t}
            testID={`tab-${t}`}
            onPress={() => setTab(t)}
            style={[styles.tab, tab === t && styles.tabActive]}
          >
            <Txt style={{ fontWeight: "700", color: tab === t ? "#fff" : colors.textPrimary, textTransform: "capitalize" }}>
              {t === "interview" ? "Mock Interview" : t}
            </Txt>
          </TouchableOpacity>
        ))}
      </View>

      {tab === "jobs" ? (
        <View style={{ gap: 12, marginTop: 16 }}>
          {jobs.length === 0 ? <Txt variant="muted">No jobs yet — check back soon.</Txt> : null}
          {jobs.map((j) => (
            <Card key={j.id}>
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                <View style={{ flex: 1 }}>
                  <Txt variant="h3">{j.title}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                    {j.employer_name} · {j.location || "Anywhere"} · {j.salary_range || ""}
                  </Txt>
                </View>
                {j.bulk_openings > 1 ? (
                  <View style={styles.badge}><Txt variant="small" style={{ fontWeight: "700", color: colors.primary }}>{j.bulk_openings} openings</Txt></View>
                ) : null}
              </View>
              <Txt variant="small" style={{ marginTop: 8, color: colors.textSecondary }} numberOfLines={2}>{j.description}</Txt>
              {j.skills_required?.length ? (
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                  {j.skills_required.slice(0, 5).map((s: string) => (
                    <View key={s} style={styles.chip}><Txt variant="small">{s}</Txt></View>
                  ))}
                </View>
              ) : null}
              <Button testID={`apply-${j.id}`} title="Apply" onPress={() => apply(j.id)} style={{ marginTop: 12 }} />
            </Card>
          ))}
        </View>
      ) : null}

      {tab === "interview" ? (
        <View style={{ gap: 12, marginTop: 16 }}>
          <Txt variant="h3">Pick a professional</Txt>
          {pros.length === 0 ? <Txt variant="muted">No professionals yet — invite some!</Txt> : null}
          {pros.map((p) => (
            <Card key={p.id}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <View style={styles.avatar}><Txt style={{ fontWeight: "800", color: "#7C3AED" }}>{(p.name || "?")[0].toUpperCase()}</Txt></View>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Txt variant="h3">{p.name}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary }}>{p.designation || ""} @ {p.company || ""}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>{(p.expertise || []).join(", ")}</Txt>
                </View>
                <Button testID={`pick-pro-${p.id}`} title="Book" onPress={() => openPro(p)} style={{ height: 40, paddingHorizontal: 14 }} />
              </View>
            </Card>
          ))}
        </View>
      ) : null}

      {tab === "applications" ? (
        <View style={{ gap: 12, marginTop: 16 }}>
          {apps.length === 0 ? <Txt variant="muted">No applications yet.</Txt> : null}
          {apps.map((a) => (
            <Card key={a.id}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <View style={{ flex: 1 }}>
                  <Txt variant="h3">{a.job_title}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                    {a.referrer_pro_name ? `Referred by ${a.referrer_pro_name}` : "Direct"} · {a.status}
                  </Txt>
                </View>
                <View style={[styles.statusPill, { backgroundColor: statusColor(a.status) }]}>
                  <Txt variant="small" style={{ color: "#fff", fontWeight: "700", textTransform: "capitalize" }}>{a.status}</Txt>
                </View>
              </View>
            </Card>
          ))}
        </View>
      ) : null}

      <Modal visible={!!selectedPro} animationType="slide" transparent onRequestClose={() => setSelectedPro(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modal}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Txt variant="h2">{selectedPro?.name}</Txt>
              <TouchableOpacity onPress={() => setSelectedPro(null)}>
                <Ionicons name="close" size={26} color={colors.textPrimary} />
              </TouchableOpacity>
            </View>
            <Txt variant="muted" style={{ marginTop: 4 }}>Available slots</Txt>
            <ScrollView style={{ marginTop: 12 }} contentContainerStyle={{ gap: 8 }}>
              {slots.length === 0 ? <Txt variant="muted">No slots available</Txt> : null}
              {slots.map((s) => (
                <TouchableOpacity key={s.id} testID={`slot-${s.id}`} onPress={() => bookSlot(s.id)}>
                  <Card style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                    <View>
                      <Txt variant="h3">{new Date(s.scheduled_at).toLocaleString()}</Txt>
                      {s.topic ? <Txt variant="small" style={{ color: colors.textSecondary }}>{s.topic}</Txt> : null}
                    </View>
                    <Ionicons name="arrow-forward-circle" size={28} color={colors.primary} />
                  </Card>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

function statusColor(s: string) {
  if (s === "hired") return colors.success;
  if (s === "rejected") return colors.error;
  if (s === "referred") return "#7C3AED";
  return colors.accent;
}

const styles = StyleSheet.create({
  tabs: { flexDirection: "row", marginTop: 16, backgroundColor: colors.surfaceAlt, borderRadius: 999, padding: 4 },
  tab: { flex: 1, paddingVertical: 10, alignItems: "center", borderRadius: 999 },
  tabActive: { backgroundColor: colors.primary },
  badge: { backgroundColor: "#FFE4E5", paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  chip: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: "#EDE9FE", alignItems: "center", justifyContent: "center" },
  statusPill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  modal: { backgroundColor: colors.bg, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, maxHeight: "80%" },
});
