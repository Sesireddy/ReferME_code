import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Alert, TouchableOpacity, Modal, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function ProRefer() {
  const [candidates, setCandidates] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [selected, setSelected] = useState<any | null>(null);
  const [jobPickerOpen, setJobPickerOpen] = useState(false);
  const [selJob, setSelJob] = useState<any | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [pool, j] = await Promise.all([
        api<any[]>("/applications/pool"),
        api<any[]>("/jobs"),
      ]);
      // Deduplicate by student_id — show each candidate once with all jobs they applied to
      const grouped: Record<string, any> = {};
      for (const a of pool) {
        const k = a.student_id;
        if (!grouped[k]) {
          grouped[k] = {
            student_id: a.student_id,
            student_name: a.student_name,
            interviews_attended: a.interviews_attended || 0,
            profile: a.student_profile || {},
            applications: [],
          };
        }
        grouped[k].applications.push({
          job_id: a.job_id,
          job_title: a.job_title,
          status: a.status,
        });
      }
      setCandidates(Object.values(grouped));
      setJobs(j);
    } catch (e: any) {
      // ignore
    }
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function refer() {
    if (!selected || !selJob) return Alert.alert("Missing", "Pick a candidate & job");
    setBusy(true);
    try {
      await api("/referrals", {
        method: "POST",
        body: { student_id: selected.student_id, job_id: selJob.id, note },
      });
      Alert.alert("Referred!", `Earn ${500} credits when ${selected.student_name} is hired.`);
      setSelected(null);
      setSelJob(null);
      setNote("");
      load();
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally {
      setBusy(false);
    }
  }

  const filtered = candidates.filter((c) => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      (c.student_name || "").toLowerCase().includes(q) ||
      (c.profile?.current_location || "").toLowerCase().includes(q) ||
      (c.profile?.skills || []).join(" ").toLowerCase().includes(q)
    );
  });

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Txt variant="h1">Refer Candidates</Txt>
      <Txt variant="muted">Browse job seekers who applied for open roles · earn 500 credits per successful referral.</Txt>

      <Input
        testID="refer-search"
        label=""
        placeholder="Search by name, location, or skill"
        value={query}
        onChangeText={setQuery}
        style={{ marginTop: 12 }}
      />

      <View style={{ gap: 12 }}>
        {filtered.length === 0 ? (
          <Card>
            <Txt variant="muted">No applicants yet. Encourage job seekers to apply!</Txt>
          </Card>
        ) : null}
        {filtered.map((c) => {
          const p = c.profile || {};
          return (
            <Card key={c.student_id}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <View style={styles.avatar}>
                  <Txt style={{ fontWeight: "800", color: "#7C3AED" }}>{(c.student_name || "?")[0].toUpperCase()}</Txt>
                </View>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Txt variant="h3">{c.student_name}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary }}>
                    {p.education || "—"}{p.passed_out_year ? ` · ${p.passed_out_year}` : ""}{p.current_location ? ` · ${p.current_location}` : ""}
                  </Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                    {p.preferred_role === "experienced"
                      ? `Experienced · ${p.years_of_experience || 0}y`
                      : "Fresher"} · Resume {p.resume_score ?? 0}/100 · {c.interviews_attended} interviews
                  </Txt>
                </View>
              </View>

              {(p.skills || []).length ? (
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
                  {(p.skills || []).slice(0, 6).map((s: string) => (
                    <View key={s} style={styles.chip}><Txt variant="small">{s}</Txt></View>
                  ))}
                </View>
              ) : null}

              {c.applications?.length ? (
                <View style={{ marginTop: 10 }}>
                  <Txt variant="small" style={{ color: colors.textSecondary }}>
                    Applied to: {c.applications.map((a: any) => a.job_title).join(", ")}
                  </Txt>
                </View>
              ) : null}

              <Button
                testID={`refer-pick-${c.student_id}`}
                title="Refer for a job"
                onPress={() => { setSelected(c); setSelJob(null); setNote(""); }}
                style={{ marginTop: 12 }}
              />
            </Card>
          );
        })}
      </View>

      <Modal visible={!!selected} transparent animationType="slide" onRequestClose={() => setSelected(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modal}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Txt variant="h2">Refer {selected?.student_name}</Txt>
              <TouchableOpacity onPress={() => setSelected(null)}>
                <Ionicons name="close" size={26} />
              </TouchableOpacity>
            </View>
            <TouchableOpacity testID="refer-job-btn" onPress={() => setJobPickerOpen(true)} style={{ marginTop: 16 }}>
              <Txt variant="label">Pick a job</Txt>
              <View style={styles.pickerBox}>
                <Txt style={{ flex: 1 }}>{selJob?.title || "Select a job"}</Txt>
                <Ionicons name="chevron-down" size={20} color={colors.textSecondary} />
              </View>
            </TouchableOpacity>
            <Input testID="refer-note" label="Note (optional)" value={note} onChangeText={setNote} placeholder="Why this candidate?" />
            <Button testID="refer-submit" title="Submit referral" onPress={refer} loading={busy} />
          </View>
        </View>
      </Modal>

      <Modal visible={jobPickerOpen} transparent animationType="slide" onRequestClose={() => setJobPickerOpen(false)}>
        <View style={styles.modalBg}>
          <View style={styles.modal}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Txt variant="h2">Pick a job</Txt>
              <TouchableOpacity onPress={() => setJobPickerOpen(false)}><Ionicons name="close" size={26} /></TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{ gap: 8, paddingTop: 12 }}>
              {jobs.map((j) => (
                <TouchableOpacity key={j.id} testID={`opt-job-${j.id}`} onPress={() => { setSelJob(j); setJobPickerOpen(false); }}>
                  <Card padding={14}>
                    <Txt variant="h3">{j.title}</Txt>
                    <Txt variant="small" style={{ color: colors.textSecondary }}>{j.employer_name} · {j.location}</Txt>
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

const styles = StyleSheet.create({
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: "#EDE9FE", alignItems: "center", justifyContent: "center" },
  chip: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  pickerBox: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceAlt, padding: 14, borderRadius: radius.md, marginTop: 6 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  modal: { backgroundColor: colors.bg, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, maxHeight: "85%" },
});
