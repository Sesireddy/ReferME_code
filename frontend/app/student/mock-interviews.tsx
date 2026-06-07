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
import { useRouter } from "expo-router";

export default function MockInterviews() {
  const router = useRouter();
  const [pros, setPros] = useState<any[]>([]);
  const [slots, setSlots] = useState<any[]>([]);
  const [selectedPro, setSelectedPro] = useState<any | null>(null);
  const [skillFilter, setSkillFilter] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const p = await api<any[]>("/professionals");
      setPros(p);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function openPro(pro: any) {
    setSelectedPro(pro);
    try {
      let q = `?pro_id=${pro.id}`;
      if (skillFilter) q += `&skill=${encodeURIComponent(skillFilter)}`;
      const s = await api<any[]>(`/interviews/slots${q}`);
      setSlots(s.filter((x) => x.status === "available"));
    } catch {
      setSlots([]);
    }
  }

  async function bookSlot(slotId: string) {
    try {
      const r = await api<{ used_free?: boolean; meeting_url?: string }>("/interviews/book", { method: "POST", body: { slot_id: slotId } });
      Alert.alert(
        "Booked ✅",
        `${r.used_free ? "Used a free token!" : "49 credits spent."}\n\nMeeting link emailed to you and shown on the dashboard.`,
      );
      setSelectedPro(null);
      load();
    } catch (e: any) {
      const msg = e.message || "";
      if (/insufficient credit/i.test(msg)) {
        Alert.alert("Insufficient credits", "Please add credits to continue booking this interview.", [
          { text: "Add Credits", onPress: () => router.push("/student/wallet") },
          { text: "Cancel", style: "cancel" },
        ]);
      } else {
        Alert.alert("Cannot book", msg);
      }
    }
  }

  // Filter pros client-side by skill if entered
  const visiblePros = pros.filter((p) => {
    if (!skillFilter.trim()) return true;
    const s = (p.expertise || []).join(" ").toLowerCase();
    return s.includes(skillFilter.toLowerCase());
  });

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Txt variant="h1">Mock Interviews</Txt>
      <Txt variant="muted">Practice with vetted professionals. 49 credits per interview.</Txt>

      <Input
        testID="mi-search"
        label=""
        placeholder="Filter by skill (e.g. React, System Design)"
        value={skillFilter}
        onChangeText={setSkillFilter}
        style={{ marginTop: 12 }}
      />

      <View style={{ gap: 12, marginTop: 12 }}>
        {visiblePros.length === 0 ? (
          <Card>
            <Txt variant="muted">No professionals match — try a different skill.</Txt>
          </Card>
        ) : null}
        {visiblePros.map((p) => (
          <Card key={p.id}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <View style={styles.avatar}>
                <Txt style={{ fontWeight: "800", color: "#7C3AED" }}>{(p.name || "?")[0].toUpperCase()}</Txt>
              </View>
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Txt variant="h3">{p.name}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>
                  {p.designation || ""}{p.company ? ` @ ${p.company}` : ""}
                </Txt>
                {(p.expertise || []).length ? (
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                    {(p.expertise || []).slice(0, 4).map((s: string) => (
                      <View key={s} style={styles.chip}><Txt variant="small">{s}</Txt></View>
                    ))}
                  </View>
                ) : null}
              </View>
              <Button testID={`pick-pro-${p.id}`} title="View slots" onPress={() => openPro(p)} style={{ height: 40, paddingHorizontal: 14 }} />
            </View>
          </Card>
        ))}
      </View>

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
              {slots.length === 0 ? <Txt variant="muted">No slots available right now.</Txt> : null}
              {slots.map((s) => (
                <TouchableOpacity key={s.id} testID={`slot-${s.id}`} onPress={() => bookSlot(s.id)}>
                  <Card style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                    <View style={{ flex: 1 }}>
                      <Txt variant="h3">{new Date(s.start_at || s.scheduled_at).toLocaleString()}</Txt>
                      {s.end_at ? (
                        <Txt variant="small" style={{ color: colors.textSecondary }}>
                          → {new Date(s.end_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </Txt>
                      ) : null}
                      {(s.skill_set || []).length ? (
                        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                          {(s.skill_set || []).join(", ")}
                        </Txt>
                      ) : null}
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

const styles = StyleSheet.create({
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: "#EDE9FE", alignItems: "center", justifyContent: "center" },
  chip: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  modal: { backgroundColor: colors.bg, borderTopLeftRadius: radius.xxl, borderTopRightRadius: radius.xxl, padding: 24, maxHeight: "80%" },
});
