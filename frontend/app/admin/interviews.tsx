import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, FlatList, Linking } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { Picker } from "@/src/components/Picker";
import { ScreenTitle } from "@/src/components/ScreenTitle";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

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
        renderItem={({ item: s }) => (
          <Card style={{ marginTop: 10 }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <View style={{ flex: 1 }}>
                <Txt variant="h3">{s.student_name || "—"} ↔ {s.pro_name || "—"}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>{(s.skill_set || []).join(", ") || "—"}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>{new Date(s.start_at).toLocaleString()}</Txt>
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
          </Card>
        )}
        ListEmptyComponent={<Txt variant="muted" style={{ marginTop: 16 }}>No interview slots found.</Txt>}
      />
    </Screen>
  );
}

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
});
