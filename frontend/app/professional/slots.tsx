import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Alert, TouchableOpacity, Modal, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { Picker } from "@/src/components/Picker";
import { DatePickerField, TimePickerField } from "@/src/components/DateTimePicker";
import { ConfirmDialog } from "@/src/components/ConfirmDialog";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { useRouter } from "expo-router";
import { EXPERIENCE_OPTIONS } from "@/src/lib/constants";

function tomorrowDateStr() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

function buildISO(date: string, time: string): Date {
  // Build local Date from YYYY-MM-DD + HH:MM (24h)
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  return new Date(y, (m || 1) - 1, d || 1, hh || 0, mm || 0, 0, 0);
}

export default function ProSlots() {
  const router = useRouter();
  const [slots, setSlots] = useState<any[]>([]);
  const [date, setDate] = useState(tomorrowDateStr());
  const [fromTime, setFromTime] = useState("11:00");
  const [toTime, setToTime] = useState("12:00");
  const [topic, setTopic] = useState("");
  const [skillSet, setSkillSet] = useState("");
  const [expYears, setExpYears] = useState("0");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [completingSlot, setCompletingSlot] = useState<any | null>(null);
  const [ratingValue, setRatingValue] = useState<number>(8);
  const [feedback, setFeedback] = useState("");
  const [submittingComplete, setSubmittingComplete] = useState(false);

  const [gmailVerified, setGmailVerified] = useState<boolean | null>(null);
  const [gmailGateOpen, setGmailGateOpen] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const s = await api<any[]>("/interviews/slots");
      setSlots(s);
      try {
        const me = await api<any>("/auth/me");
        setGmailVerified(!!me?.user?.gmail_verified);
      } catch {}
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function createSlot() {
    // Gmail verification gate
    if (gmailVerified === false) {
      setGmailGateOpen(true);
      return;
    }
    const skillArr = skillSet.split(",").map((s) => s.trim()).filter(Boolean);
    if (skillArr.length === 0) {
      return Alert.alert("Skill Set is required.");
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return Alert.alert("Invalid date", "Use YYYY-MM-DD");
    }
    if (!/^\d{1,2}:\d{2}$/.test(fromTime) || !/^\d{1,2}:\d{2}$/.test(toTime)) {
      return Alert.alert("Invalid time", "Use HH:MM (24h)");
    }
    const start = buildISO(date, fromTime);
    const end = buildISO(date, toTime);
    if (isNaN(start.getTime()) || isNaN(end.getTime())) {
      return Alert.alert("Invalid date/time");
    }
    if (end <= start) {
      return Alert.alert("Invalid range", "End must be after start.");
    }
    if (start.getTime() <= Date.now()) {
      return Alert.alert("Pick future time", "Slot must be in the future.");
    }
    setBusy(true);
    try {
      await api("/interviews/slots", {
        method: "POST",
        body: {
          start_at: start.toISOString(),
          end_at: end.toISOString(),
          topic,
          skill_set: skillArr,
          experience_years: parseInt(expYears || "0", 10),
        },
      });
      setTopic("");
      Alert.alert("Slot created", `${fromTime} – ${toTime} on ${date}`);
      load();
    } catch (e: any) {
      Alert.alert("Cannot create slot", e.message);
    } finally {
      setBusy(false);
    }
  }

  async function complete(slot: any) {
    setCompletingSlot(slot);
    setRatingValue(8);
    setFeedback("");
  }

  async function submitComplete() {
    if (!completingSlot) return;
    if (ratingValue < 1 || ratingValue > 10) {
      return Alert.alert("Pick a rating", "Rating must be 1-10");
    }
    setSubmittingComplete(true);
    try {
      const r = await api<any>(`/interviews/${completingSlot.id}/complete`, {
        method: "POST",
        body: { rating: ratingValue, feedback },
      });
      setCompletingSlot(null);
      Alert.alert("Earned", `+${r.earned} credits\nCandidate rated ${r.candidate_rating}/10\nYour rating: ${r.pro_rating}/10`);
      load();
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally {
      setSubmittingComplete(false);
    }
  }

  function fmtRange(s: any): string {
    const start = s.start_at || s.scheduled_at;
    if (!start) return "";
    const sd = new Date(start);
    const datePart = sd.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
    const startTime = sd.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (s.end_at) {
      const ed = new Date(s.end_at);
      const endTime = ed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      return `${datePart} · ${startTime} – ${endTime}`;
    }
    return `${datePart} · ${startTime}`;
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Txt variant="h1">My Interviews</Txt>
      <Card style={{ marginTop: 16 }}>
        <Txt variant="h3">Create a slot</Txt>
        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2, marginBottom: 12 }}>
          Pick a date and From / To time. Overlapping slots are not allowed.
        </Txt>
        <DatePickerField testID="slot-date" label="Date" value={date} onChange={setDate} />
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}>
            <TimePickerField testID="slot-from" label="From" value={fromTime} onChange={setFromTime} />
          </View>
          <View style={{ flex: 1 }}>
            <TimePickerField testID="slot-to" label="To" value={toTime} onChange={setToTime} />
          </View>
        </View>
        <Input testID="slot-topic" label="Topic (optional)" placeholder="System design / Behavioral" value={topic} onChangeText={setTopic} />
        <Input testID="slot-skills" label="Skill Set (comma-separated) *" placeholder="React, System Design" value={skillSet} onChangeText={setSkillSet} />
        <Picker
          testID="slot-exp"
          label="Your Total Experience"
          options={EXPERIENCE_OPTIONS}
          value={expYears}
          onChange={(v) => setExpYears(v as string)}
          placeholder="Select experience"
        />
        <Txt variant="small" style={{ color: colors.textSecondary, marginBottom: 8 }}>
          Slots use 12-hour AM/PM in IST. Min 1 hour, max 5 hours/day per professional.
        </Txt>
        <Button testID="create-slot" title="Create slot" onPress={createSlot} loading={busy} />
      </Card>

      <Txt variant="h3" style={{ marginTop: 24, marginBottom: 8 }}>Your slots</Txt>
      <View style={{ gap: 8 }}>
        {slots.length === 0 ? <Txt variant="muted">No slots yet.</Txt> : null}
        {slots.map((s) => (
          <Card key={s.id}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <View style={{ flex: 1 }}>
                <Txt variant="h3">{fmtRange(s)}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>{s.topic || "—"}</Txt>
                <Txt variant="small" style={{ marginTop: 2 }}>
                  {s.status === "available" ? "Awaiting booking" : s.status === "booked" ? `Booked by ${s.student_name}` : "Completed"}
                </Txt>
              </View>
              {s.status === "booked" ? (
                <Button testID={`complete-${s.id}`} title="Done" onPress={() => complete(s)} style={{ height: 40, paddingHorizontal: 14 }} />
              ) : (
                <View style={[styles.pill, { backgroundColor: s.status === "completed" ? colors.success : colors.surfaceAlt }]}>
                  <Txt variant="small" style={{ color: s.status === "completed" ? "#fff" : colors.textSecondary, fontWeight: "700" }}>{s.status}</Txt>
                </View>
              )}
            </View>
          </Card>
        ))}
      </View>

      <Modal visible={!!completingSlot} transparent animationType="slide" onRequestClose={() => setCompletingSlot(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalSheet}>
            <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 6 }}>
              <Ionicons name="star" size={22} color="#FFB347" />
              <Txt variant="h2" style={{ marginLeft: 8 }}>Rate the candidate</Txt>
            </View>
            <Txt variant="small" style={{ color: colors.textSecondary, marginBottom: 12 }}>
              {completingSlot?.student_name} · {fmtRange(completingSlot || {})}
            </Txt>
            <Txt variant="label" style={{ marginBottom: 6 }}>Score (1–10)</Txt>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 14 }}>
              {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                <TouchableOpacity
                  key={n}
                  testID={`rating-${n}`}
                  onPress={() => setRatingValue(n)}
                  style={[styles.rateBtn, ratingValue === n ? styles.rateBtnActive : null]}
                >
                  <Txt style={{ fontWeight: "700", color: ratingValue === n ? "#fff" : colors.textPrimary }}>{n}</Txt>
                </TouchableOpacity>
              ))}
            </ScrollView>
            <Input
              testID="feedback"
              label="Feedback (optional)"
              placeholder="Strengths, areas to improve…"
              value={feedback}
              onChangeText={setFeedback}
              multiline
            />
            <View style={{ height: 8 }} />
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Button title="Cancel" variant="secondary" onPress={() => setCompletingSlot(null)} style={{ flex: 1 }} />
              <Button testID="submit-complete" title={`Mark Done · +35`} onPress={submitComplete} loading={submittingComplete} style={{ flex: 1 }} />
            </View>
            <Txt variant="small" style={{ marginTop: 8, color: colors.textSecondary, textAlign: "center" }}>
              Requires both participants to have joined the session and a minimum 15 minutes since the scheduled start.
            </Txt>
          </View>
        </View>
      </Modal>

      <ConfirmDialog
        visible={gmailGateOpen}
        title="Gmail verification is required before creating a Mock Interview slot."
        confirmLabel="Verify Gmail"
        cancelLabel="Cancel"
        onCancel={() => setGmailGateOpen(false)}
        onConfirm={() => { setGmailGateOpen(false); router.push("/professional/profile"); }}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  pill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  modalSheet: { backgroundColor: colors.bg, padding: 20, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: "85%" },
  rateBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceAlt, marginRight: 8 },
  rateBtnActive: { backgroundColor: "#7C3AED" },
});
