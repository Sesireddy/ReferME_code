import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Alert, TouchableOpacity, Modal, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { ScreenTitle } from "@/src/components/ScreenTitle";
import { Button } from "@/src/components/Button";
import { SkillAutocomplete } from "@/src/components/SkillAutocomplete";
import { DatePickerField } from "@/src/components/DateTimePicker";
import { ConfirmDialog } from "@/src/components/ConfirmDialog";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { successAlert } from "@/src/lib/successAlert";
import { useRouter } from "expo-router";

// Format a slot's time range like "10:00 AM – 10:30 AM"
function fmtSlotRange(start: string, end?: string) {
  const opts: Intl.DateTimeFormatOptions = { hour: "numeric", minute: "2-digit", hour12: true };
  const s = new Date(start);
  const e = end ? new Date(end) : null;
  const sStr = s.toLocaleTimeString([], opts);
  if (!e) return sStr;
  return `${sStr} – ${e.toLocaleTimeString([], opts)}`;
}

function fmtDateHeader(start: string) {
  const d = new Date(start);
  return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

export default function MockInterviews() {
  const router = useRouter();
  const [pros, setPros] = useState<any[]>([]);
  const [slots, setSlots] = useState<any[]>([]);
  const [myBookings, setMyBookings] = useState<{ start_at: string; end_at: string }[]>([]);
  const [selectedPro, setSelectedPro] = useState<any | null>(null);
  // Iter 72 — inside the pro's slot modal, first pick a date, then see slots
  // for that date (mirrors the pro-side date-grouped view for symmetry).
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [pendingBookSlotId, setPendingBookSlotId] = useState<string | null>(null);
  const [bookSuccessOpen, setBookSuccessOpen] = useState(false);
  const [skillFilter, setSkillFilter] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [topicFilter, setTopicFilter] = useState<string | null>(null); // Iter 71
  const [refreshing, setRefreshing] = useState(false);
  const [actionCost, setActionCost] = useState<number>(99);

  // Fetch the current user's per-action credit cost. Iter 67: standardized 99
  // credits for ALL Job Seekers (fresher & experienced). Backend still returns
  // the value via `/auth/me.user.action_cost` so we read it dynamically.
  useEffect(() => {
    (async () => {
      try {
        const r = await api<{ user?: { action_cost?: number } }>("/auth/me");
        if (typeof r?.user?.action_cost === "number") setActionCost(r.user.action_cost);
      } catch {}
    })();
  }, []);

  // Two ISO time ranges [a1,a2) and [b1,b2) overlap iff a1<b2 AND a2>b1
  const hasOverlap = useCallback(
    (start: string, end: string): boolean => {
      if (!start || !end) return false;
      const s = new Date(start).getTime();
      const e = new Date(end).getTime();
      return myBookings.some((b) => {
        const bs = new Date(b.start_at).getTime();
        const be = new Date(b.end_at).getTime();
        return s < be && e > bs;
      });
    },
    [myBookings],
  );

  const loadMyBookings = useCallback(async () => {
    try {
      const r = await api<any[]>("/interviews/my-bookings");
      const active = (r || []).filter((b) => b.status === "booked" || b.status === "completed");
      setMyBookings(active.map((b) => ({ start_at: b.start_at, end_at: b.end_at })));
    } catch {
      // ignore
    }
  }, []);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams({ has_available_slots: "true" });
      if (skillFilter.trim()) params.set("skill", skillFilter.trim());
      if (dateFilter) params.set("date", dateFilter);
      if (topicFilter) params.set("topic", topicFilter);
      const [p] = await Promise.all([
        api<any[]>(`/professionals?${params.toString()}`),
        loadMyBookings(),
      ]);
      setPros(p);
    } catch {
      setPros([]);
    }
    setRefreshing(false);
  }, [skillFilter, dateFilter, topicFilter, loadMyBookings]);

  useEffect(() => { load(); }, [load]);

  async function openPro(pro: any) {
    if (pro.fully_booked) return; // disabled
    setSelectedPro(pro);
    setSelectedDate(null); // Iter 72 — start at the date list, drill into a date on tap
    try {
      const params = new URLSearchParams({ pro_id: pro.id });
      if (skillFilter) params.set("skill", skillFilter);
      if (dateFilter) params.set("date", dateFilter);
      if (topicFilter) params.set("topic", topicFilter);
      const s = await api<any[]>(`/interviews/slots?${params.toString()}`);
      // Backend already excludes expired & cancelled for students drilling into a pro.
      setSlots(s);
    } catch {
      setSlots([]);
    }
  }

  async function refreshOpenProSlots(proId: string) {
    try {
      const params = new URLSearchParams({ pro_id: proId });
      const s = await api<any[]>(`/interviews/slots?${params.toString()}`);
      setSlots(s);
    } catch {
      /* ignore */
    }
  }

  async function bookSlot(slotId: string) {
    setPendingBookSlotId(slotId);
  }

  async function confirmBookSlot() {
    if (!pendingBookSlotId) return;
    const slotId = pendingBookSlotId;
    // Client-side guard: if the slot's range overlaps with an existing booking, block immediately.
    const slotObj = slots.find((s) => s.id === slotId);
    if (slotObj && hasOverlap(slotObj.start_at, slotObj.end_at)) {
      setPendingBookSlotId(null);
      successAlert.show({
        title: "Booking Not Allowed",
        message: "You already have a mock interview scheduled during this time. Please select a different time slot.",
        intent: "warning",
      });
      return;
    }
    setPendingBookSlotId(null);
    try {
      await api<{ used_free?: boolean; meeting_url?: string }>("/interviews/book", { method: "POST", body: { slot_id: slotId } });
      setBookSuccessOpen(true);
      // Refresh bookings to update Time Conflict markers
      loadMyBookings();
      // Refresh the open pro's slot grid AND the outer listing so "fully_booked" updates immediately.
      if (selectedPro) await refreshOpenProSlots(selectedPro.id);
      load();
    } catch (e: any) {
      const msg = e.message || "";
      if (/already have a mock interview/i.test(msg) || /schedul.*during this time/i.test(msg)) {
        successAlert.show({
          title: "Booking Not Allowed",
          message: "You already have a mock interview scheduled during this time. Please select a different time slot.",
          intent: "warning",
        });
        loadMyBookings();
      } else if (/insufficient credit/i.test(msg)) {
        Alert.alert(
          "Insufficient Credits",
          "You don't have enough credits to continue. Please purchase additional credits.",
          [
            { text: "Buy Credits", onPress: () => router.push("/student/wallet") },
            { text: "Cancel", style: "cancel" },
          ],
        );
      } else {
        Alert.alert("Cannot book", msg);
      }
    }
  }

  // Group slots by date so the modal shows per-day buckets (matches the spec table format).
  const groupedSlots: { date: string; items: any[] }[] = (() => {
    const buckets: Record<string, any[]> = {};
    for (const s of slots) {
      const k = new Date(s.start_at || s.scheduled_at).toDateString();
      (buckets[k] ||= []).push(s);
    }
    return Object.entries(buckets).map(([k, v]) => ({
      date: k,
      items: v.sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime()),
    }));
  })();

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <ScreenTitle title="Mock Interviews" icon="mic" color={colors.primary} subtitle={`Practice with vetted professionals. ${actionCost} credits per interview.`} />

      <View style={{ marginTop: 12 }}>
        {/* Iter 72 — Skill Set filter only for Technical Discussion (and default no-topic) */}
        {topicFilter !== "Career Guidance" && topicFilter !== "HR Discussion" ? (
          <SkillAutocomplete
            testID="mi-search"
            value={skillFilter}
            onChange={setSkillFilter}
            placeholder="Search or Select Skill"
          />
        ) : null}
      </View>
      <View style={{ flexDirection: "row", gap: 8 }}>
        <View style={{ flex: 1 }}>
          <DatePickerField testID="mi-date" value={dateFilter} onChange={setDateFilter} placeholder="Filter by date" />
        </View>
      </View>
      {dateFilter ? (
        <TouchableOpacity testID="mi-clear-date" onPress={() => setDateFilter("")} style={{ alignSelf: "flex-end", paddingVertical: 4, marginBottom: 4 }}>
          <Txt variant="small" style={{ color: colors.primary }}>Clear date filter</Txt>
        </TouchableOpacity>
      ) : null}

      {/* Iter 71 — Topic filter chips */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 4 }}>
        {[
          { v: null, label: "All Topics" },
          { v: "Career Guidance", label: "🧭 Career Guidance" },
          { v: "Technical Discussion", label: "💻 Technical" },
          { v: "HR Discussion", label: "👥 HR" },
        ].map((f) => {
          const active = topicFilter === f.v;
          return (
            <TouchableOpacity
              key={String(f.v)}
              onPress={() => {
                setTopicFilter(f.v);
                // Iter 72 — Clear skill filter when switching to a non-technical
                // topic; the skill filter only makes sense for Technical Discussion.
                if (f.v === "Career Guidance" || f.v === "HR Discussion") {
                  setSkillFilter("");
                }
              }}
              style={[styles.topicFilterChip, active && styles.topicFilterChipActive]}
              testID={`mi-topic-${f.v ?? "all"}`}
              activeOpacity={0.7}
            >
              <Txt style={[styles.topicFilterChipTxt, active && { color: "#fff" }]}>{f.label}</Txt>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

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
        {pros.map((p) => {
          const fully = !!p.fully_booked;
          return (
            <Card key={p.id}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <View style={styles.avatar}>
                  <Txt style={{ fontWeight: "800", color: "#7C3AED" }}>{(p.name || "?")[0].toUpperCase()}</Txt>
                </View>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Txt variant="h3">{p.name}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary }}>
                    {p.designation || ""}{p.company ? ` @ ${p.company}` : ""}
                    {p.experience_years ? ` • ${p.experience_years} Years Experience` : ""}
                  </Txt>
                  {(p.expertise || []).length ? (
                    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                      {(p.expertise || []).slice(0, 4).map((s: string) => (
                        <View key={s} style={styles.chip}><Txt variant="small">{s}</Txt></View>
                      ))}
                    </View>
                  ) : null}
                  {p.slots_total ? (
                    <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>
                      {p.slots_available} of {p.slots_total} slots available
                    </Txt>
                  ) : null}
                </View>
                {fully ? (
                  <View testID={`pro-booked-${p.id}`} style={styles.bookedPill}>
                    <Ionicons name="lock-closed" size={14} color="#9CA3AF" />
                    <Txt style={{ marginLeft: 4, color: "#9CA3AF", fontWeight: "700" }}>Booked</Txt>
                  </View>
                ) : (
                  <Button testID={`pick-pro-${p.id}`} title="View Slots" onPress={() => openPro(p)} style={{ height: 40, paddingHorizontal: 14 }} />
                )}
              </View>
            </Card>
          );
        })}
      </View>

      <Modal
        visible={!!selectedPro}
        animationType="slide"
        transparent
        onRequestClose={() => {
          // Iter 72 — one-step back inside modal: if on the slots view, go
          // back to the dates view first; otherwise close the modal.
          if (selectedDate) setSelectedDate(null);
          else setSelectedPro(null);
        }}
      >
        <View style={styles.modalBg}>
          <View style={styles.modal}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <TouchableOpacity
                onPress={() => (selectedDate ? setSelectedDate(null) : setSelectedPro(null))}
                hitSlop={10}
                style={{ paddingRight: 8 }}
                testID="modal-back"
              >
                <Ionicons
                  name={selectedDate ? "chevron-back" : "close"}
                  size={26}
                  color={colors.textPrimary}
                />
              </TouchableOpacity>
              <View style={{ flex: 1 }}>
                <Txt variant="h2">{selectedPro?.name}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>
                  {selectedDate
                    ? fmtDateHeader(groupedSlots.find((g) => g.date === selectedDate)?.items[0]?.start_at || selectedDate)
                    : `${selectedPro?.designation || ""}${selectedPro?.company ? ` @ ${selectedPro.company}` : ""}`}
                </Txt>
              </View>
            </View>
            <Txt variant="muted" style={{ marginTop: 4 }}>
              {selectedDate ? "Available time slots" : "Pick a date to see available slots"}
            </Txt>

            <ScrollView style={{ marginTop: 12 }} contentContainerStyle={{ gap: 8 }}>
              {slots.length === 0 ? (
                <Txt variant="muted">No slots available right now.</Txt>
              ) : null}

              {/* Level 1 — date summary cards */}
              {!selectedDate
                ? groupedSlots.map((g) => {
                    const available = g.items.filter((x) => x.status !== "booked" && x.status !== "completed").length;
                    if (available === 0) return null; // hide dates with no availability
                    return (
                      <Card key={g.date} style={{ padding: 14 }}>
                        <TouchableOpacity
                          testID={`date-${g.date}`}
                          onPress={() => setSelectedDate(g.date)}
                          activeOpacity={0.7}
                          style={{ flexDirection: "row", alignItems: "center" }}
                        >
                          <View style={{ flex: 1 }}>
                            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                              <Ionicons name="calendar" size={16} color="#7C3AED" />
                              <Txt variant="h3" style={{ fontSize: 15 }}>
                                {fmtDateHeader(g.items[0]?.start_at || g.date)}
                              </Txt>
                            </View>
                            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>
                              Available Slots: {available}
                            </Txt>
                          </View>
                          <View style={styles.viewSlotsBtn}>
                            <Txt style={{ color: "#fff", fontWeight: "700", fontSize: 13 }}>View Slots</Txt>
                            <Ionicons name="chevron-forward" size={16} color="#fff" />
                          </View>
                        </TouchableOpacity>
                      </Card>
                    );
                  })
                : null}

              {/* Level 2 — actual time slots for the selected date */}
              {selectedDate
                ? (groupedSlots.find((g) => g.date === selectedDate)?.items || [])
                    .filter((s) => s.status !== "booked" && s.status !== "completed")
                    .map((s) => {
                      const conflict = hasOverlap(s.start_at, s.end_at);
                      return (
                        <Card key={s.id} style={styles.slotRow}>
                          <View style={{ flex: 1 }}>
                            <Txt variant="h3" style={{ fontSize: 16 }}>{fmtSlotRange(s.start_at, s.end_at)}</Txt>
                            {s.topic ? (
                              <View style={styles.topicPill}>
                                <Ionicons
                                  name={
                                    s.topic === "Technical Discussion"
                                      ? "code-slash"
                                      : s.topic === "HR Discussion"
                                      ? "people-circle"
                                      : "compass"
                                  }
                                  size={12}
                                  color="#7C3AED"
                                />
                                <Txt style={{ marginLeft: 4, color: "#7C3AED", fontWeight: "700", fontSize: 11 }}>
                                  {s.topic}
                                </Txt>
                              </View>
                            ) : null}
                            {(s.skill_set || []).length ? (
                              <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                                {(s.skill_set || []).join(", ")}
                              </Txt>
                            ) : null}
                            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                              With {selectedPro?.name}
                            </Txt>
                          </View>
                          {conflict ? (
                            <View testID={`slot-${s.id}-conflict`} style={styles.conflictTag}>
                              <Ionicons name="warning" size={14} color={colors.warning} />
                              <Txt style={{ marginLeft: 4, color: colors.warning, fontWeight: "700", fontSize: 12 }}>Time Conflict</Txt>
                            </View>
                          ) : (
                            <Button
                              testID={`slot-${s.id}-book`}
                              title="Book Now"
                              onPress={() => bookSlot(s.id)}
                              style={{ height: 36, paddingHorizontal: 18 }}
                            />
                          )}
                        </Card>
                      );
                    })
                : null}
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
        title="Mock Interview Booked"
        message="Your mock interview has been booked successfully. Meeting invitation has been sent to both participants."
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
  modal: { backgroundColor: colors.bg, borderTopLeftRadius: radius.xxl, borderTopRightRadius: radius.xxl, padding: 24, maxHeight: "82%" },
  bookedPill: { flexDirection: "row", alignItems: "center", backgroundColor: "#F3F4F6", borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: "#E5E7EB" },
  bookedTag: { flexDirection: "row", alignItems: "center", backgroundColor: "#F3F4F6", borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: "#E5E7EB" },
  conflictTag: { flexDirection: "row", alignItems: "center", backgroundColor: "#FEF3C7", borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: "#FDE68A" },
  slotRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  topicPill: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    backgroundColor: "#F5F3FF",
    borderWidth: 1,
    borderColor: "#7C3AED40",
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 3,
    marginTop: 4,
  },
  topicFilterChip: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 999,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  topicFilterChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  topicFilterChipTxt: { fontSize: 12, fontWeight: "700", color: colors.textPrimary },
  viewSlotsBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: "#7C3AED",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
  },
});
