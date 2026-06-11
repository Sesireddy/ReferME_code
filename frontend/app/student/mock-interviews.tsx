import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Alert, TouchableOpacity, Modal, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { Picker } from "@/src/components/Picker";
import { DatePickerField } from "@/src/components/DateTimePicker";
import { ConfirmDialog } from "@/src/components/ConfirmDialog";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { useRouter } from "expo-router";

export default function MockInterviews() {
  const router = useRouter();
  const [pros, setPros] = useState<any[]>([]);
  const [slots, setSlots] = useState<any[]>([]);
  const [selectedPro, setSelectedPro] = useState<any | null>(null);
  const [pendingBookSlotId, setPendingBookSlotId] = useState<string | null>(null);
  const [bookSuccessOpen, setBookSuccessOpen] = useState(false);
  const [skillFilter, setSkillFilter] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string | null>("");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      // Only fetch pros who CURRENTLY have available, future slots — backend filters this.
      const params = new URLSearchParams({ has_available_slots: "true" });
      if (skillFilter.trim()) params.set("skill", skillFilter.trim());
      if (dateFilter) params.set("date", dateFilter);
      if (categoryFilter) params.set("category", categoryFilter);
      const p = await api<any[]>(`/professionals?${params.toString()}`);
      setPros(p);
    } catch {
      setPros([]);
    }
    setRefreshing(false);
  }, [skillFilter, dateFilter, categoryFilter]);

  useEffect(() => { load(); }, [load]);

  async function openPro(pro: any) {
    setSelectedPro(pro);
    try {
      const params = new URLSearchParams({ pro_id: pro.id });
      if (skillFilter) params.set("skill", skillFilter);
      if (dateFilter) params.set("date", dateFilter);
      if (categoryFilter) params.set("category", categoryFilter);
      const s = await api<any[]>(`/interviews/slots?${params.toString()}`);
      setSlots(s.filter((x) => x.status === "available"));
    } catch {
      setSlots([]);
    }
  }

  async function bookSlot(slotId: string) {
    setPendingBookSlotId(slotId);
  }

  async function confirmBookSlot() {
    if (!pendingBookSlotId) return;
    const slotId = pendingBookSlotId;
    setPendingBookSlotId(null);
    try {
      const r = await api<{ used_free?: boolean; meeting_url?: string }>("/interviews/book", { method: "POST", body: { slot_id: slotId } });
      setSelectedPro(null);
      setBookSuccessOpen(true);
      void r;
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

  // Pros are already filtered server-side by skill + date + category, and only those
  // with currently available future slots are returned. No additional client filter needed.

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
      <View style={{ flexDirection: "row", gap: 8 }}>
        <View style={{ flex: 1 }}>
          <DatePickerField testID="mi-date" value={dateFilter} onChange={setDateFilter} placeholder="Filter by date" />
        </View>
        <View style={{ flex: 1 }}>
          <Picker
            testID="mi-category"
            options={[
              { value: "", label: "All categories" },
              { value: "fresher", label: "Fresher" },
              { value: "experienced", label: "Experienced" },
            ]}
            value={categoryFilter}
            onChange={(v) => setCategoryFilter(v as string)}
            placeholder="Category"
          />
        </View>
      </View>
      {dateFilter ? (
        <TouchableOpacity testID="mi-clear-date" onPress={() => setDateFilter("")} style={{ alignSelf: "flex-end", paddingVertical: 4, marginBottom: 4 }}>
          <Txt variant="small" style={{ color: colors.primary }}>Clear date filter</Txt>
        </TouchableOpacity>
      ) : null}

      <View style={{ gap: 12, marginTop: 12 }}>
        {pros.length === 0 ? (
          <Card>
            <Txt variant="muted">
              {dateFilter || skillFilter
                ? "No professionals available with these filters."
                : "No professionals currently available — check back later."}
            </Txt>
          </Card>
        ) : null}
        {pros.map((p) => (
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

      <ConfirmDialog
        visible={!!pendingBookSlotId}
        title="Do you want to book this mock interview slot?"
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        onCancel={() => setPendingBookSlotId(null)}
        onConfirm={confirmBookSlot}
      />
      <ConfirmDialog
        visible={bookSuccessOpen}
        title="Mock Interview booked successfully."
        confirmLabel="OK"
        cancelLabel=""
        onCancel={() => setBookSuccessOpen(false)}
        onConfirm={() => setBookSuccessOpen(false)}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: "#EDE9FE", alignItems: "center", justifyContent: "center" },
  chip: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  modal: { backgroundColor: colors.bg, borderTopLeftRadius: radius.xxl, borderTopRightRadius: radius.xxl, padding: 24, maxHeight: "80%" },
});
