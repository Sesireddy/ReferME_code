import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Alert, TouchableOpacity, Modal, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function ProRefer() {
  const [students, setStudents] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [selStu, setSelStu] = useState<any | null>(null);
  const [selJob, setSelJob] = useState<any | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [picker, setPicker] = useState<"student" | "job" | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [s, j] = await Promise.all([
        api<any[]>("/leaderboard/students"),
        api<any[]>("/jobs"),
      ]);
      setStudents(s);
      setJobs(j);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function refer() {
    if (!selStu || !selJob) return Alert.alert("Missing", "Pick student & job");
    setBusy(true);
    try {
      await api("/referrals", { method: "POST", body: { student_id: selStu.id, job_id: selJob.id, note } });
      Alert.alert("Referred!", "Earn 500 credits if hired.");
      setSelStu(null); setSelJob(null); setNote("");
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally { setBusy(false); }
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Txt variant="h1">Refer Candidate</Txt>
      <Txt variant="muted">Refer top students to open roles · +500 credits when hired</Txt>

      <Card style={{ marginTop: 16 }}>
        <TouchableOpacity testID="pick-student-btn" onPress={() => setPicker("student")}>
          <Txt variant="label">Student</Txt>
          <View style={styles.pickerBox}>
            <Txt style={{ flex: 1 }}>{selStu?.name || "Select a student"}</Txt>
            <Ionicons name="chevron-down" size={20} color={colors.textSecondary} />
          </View>
        </TouchableOpacity>

        <TouchableOpacity testID="pick-job-btn" onPress={() => setPicker("job")} style={{ marginTop: 12 }}>
          <Txt variant="label">Job</Txt>
          <View style={styles.pickerBox}>
            <Txt style={{ flex: 1 }}>{selJob?.title || "Select a job"}</Txt>
            <Ionicons name="chevron-down" size={20} color={colors.textSecondary} />
          </View>
        </TouchableOpacity>

        <Input testID="refer-note" label="Note (optional)" value={note} onChangeText={setNote} placeholder="Why this candidate?" />
        <Button testID="refer-submit" title="Submit referral" onPress={refer} loading={busy} />
      </Card>

      <Modal visible={!!picker} transparent animationType="slide" onRequestClose={() => setPicker(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modal}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Txt variant="h2">{picker === "student" ? "Pick student" : "Pick job"}</Txt>
              <TouchableOpacity onPress={() => setPicker(null)}><Ionicons name="close" size={26} /></TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{ gap: 8, paddingTop: 12 }}>
              {picker === "student"
                ? students.map((s) => (
                    <TouchableOpacity key={s.id} testID={`opt-stu-${s.id}`} onPress={() => { setSelStu(s); setPicker(null); }}>
                      <Card padding={14}>
                        <Txt variant="h3">{s.name}</Txt>
                        <Txt variant="small" style={{ color: colors.textSecondary }}>Resume score {s.resume_score} · {s.interviews_attended} interviews</Txt>
                      </Card>
                    </TouchableOpacity>
                  ))
                : jobs.map((j) => (
                    <TouchableOpacity key={j.id} testID={`opt-job-${j.id}`} onPress={() => { setSelJob(j); setPicker(null); }}>
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
  pickerBox: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceAlt, padding: 14, borderRadius: 12, marginTop: 6 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  modal: { backgroundColor: colors.bg, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, maxHeight: "80%" },
});
