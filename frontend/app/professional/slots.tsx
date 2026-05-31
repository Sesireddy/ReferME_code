import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Alert, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

function tomorrowDateStr() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

function buildISO(date: string, time: string): Date {
  // Build local Date from YYYY-MM-DD + HH:MM (24h)
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  return new Date(y, (m || 1) - 1, d || 1, hh || 0, mm || 0, 0, 0);
}

export default function ProSlots() {
  const [slots, setSlots] = useState<any[]>([]);
  const [date, setDate] = useState(tomorrowDateStr());
  const [fromTime, setFromTime] = useState("11:00");
  const [toTime, setToTime] = useState("12:00");
  const [topic, setTopic] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const s = await api<any[]>("/interviews/slots");
      setSlots(s);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function createSlot() {
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

  async function complete(slotId: string) {
    try {
      const r = await api<any>(`/interviews/${slotId}/complete`, { method: "POST" });
      Alert.alert("Earned", `+${r.earned} credits`);
      load();
    } catch (e: any) {
      Alert.alert("Failed", e.message);
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
        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2, marginBottom: 8 }}>
          Pick a date and From / To time. Overlapping slots are not allowed.
        </Txt>
        <Input testID="slot-date" label="Date" placeholder="YYYY-MM-DD" value={date} onChangeText={setDate} />
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Input testID="slot-from" label="From (HH:MM)" placeholder="11:00" value={fromTime} onChangeText={setFromTime} />
          </View>
          <View style={{ flex: 1 }}>
            <Input testID="slot-to" label="To (HH:MM)" placeholder="12:00" value={toTime} onChangeText={setToTime} />
          </View>
        </View>
        <Input testID="slot-topic" label="Topic (optional)" placeholder="System design / Behavioral" value={topic} onChangeText={setTopic} />
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
                <Button testID={`complete-${s.id}`} title="Done" onPress={() => complete(s.id)} style={{ height: 40, paddingHorizontal: 14 }} />
              ) : (
                <View style={[styles.pill, { backgroundColor: s.status === "completed" ? colors.success : colors.surfaceAlt }]}>
                  <Txt variant="small" style={{ color: s.status === "completed" ? "#fff" : colors.textSecondary, fontWeight: "700" }}>{s.status}</Txt>
                </View>
              )}
            </View>
          </Card>
        ))}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  pill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 },
});
