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

function isoForInDays(days: number, hour = 11) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  d.setHours(hour, 0, 0, 0);
  return d.toISOString();
}

export default function ProSlots() {
  const [slots, setSlots] = useState<any[]>([]);
  const [date, setDate] = useState(isoForInDays(1).slice(0, 10));
  const [time, setTime] = useState("11:00");
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
    setBusy(true);
    try {
      const dt = new Date(`${date}T${time}:00`);
      if (isNaN(dt.getTime())) {
        Alert.alert("Invalid date/time");
      } else {
        await api("/interviews/slots", { method: "POST", body: { scheduled_at: dt.toISOString(), topic } });
        setTopic("");
        load();
      }
    } catch (e: any) {
      Alert.alert("Failed", e.message);
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

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Txt variant="h1">My Interviews</Txt>
      <Card style={{ marginTop: 16 }}>
        <Txt variant="h3">Create a slot</Txt>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}><Input testID="slot-date" label="Date" placeholder="YYYY-MM-DD" value={date} onChangeText={setDate} /></View>
          <View style={{ flex: 1 }}><Input testID="slot-time" label="Time" placeholder="HH:MM" value={time} onChangeText={setTime} /></View>
        </View>
        <Input testID="slot-topic" label="Topic" placeholder="System design / Behavioral" value={topic} onChangeText={setTopic} />
        <Button testID="create-slot" title="Create slot" onPress={createSlot} loading={busy} />
      </Card>

      <Txt variant="h3" style={{ marginTop: 24, marginBottom: 8 }}>Your slots</Txt>
      <View style={{ gap: 8 }}>
        {slots.length === 0 ? <Txt variant="muted">No slots yet.</Txt> : null}
        {slots.map((s) => (
          <Card key={s.id}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <View style={{ flex: 1 }}>
                <Txt variant="h3">{new Date(s.scheduled_at).toLocaleString()}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>{s.topic || "—"}</Txt>
                <Txt variant="small" style={{ marginTop: 2 }}>{s.status === "available" ? "Awaiting booking" : s.status === "booked" ? `Booked by ${s.student_name}` : "Completed"}</Txt>
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
