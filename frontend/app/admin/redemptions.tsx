import React, { useEffect, useState, useCallback, useMemo } from "react";
import { View, StyleSheet, TouchableOpacity, FlatList, Modal, Alert, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { ScreenTitle } from "@/src/components/ScreenTitle";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { successAlert } from "@/src/lib/successAlert";

type Req = {
  id: string;
  pro_name: string;
  pro_email: string;
  credits_requested: number;
  amount_inr: number;
  available_credits_at_request: number;
  account_holder_name: string;
  upi_id: string;
  bank_account?: string;
  ifsc?: string;
  status: "pending" | "approved" | "paid" | "rejected";
  payment_ref?: string;
  payment_date?: string;
  remarks?: string;
  rejection_reason?: string;
  created_at: string;
};

const STATUS_TABS: Array<{ key: string; label: string; ion: any }> = [
  { key: "pending", label: "Pending", ion: "hourglass" },
  { key: "approved", label: "Approved", ion: "checkmark-circle" },
  { key: "paid", label: "Paid", ion: "wallet" },
  { key: "rejected", label: "Rejected", ion: "close-circle" },
  { key: "all", label: "All", ion: "list" },
];

function statusColor(s: string): string {
  if (s === "approved") return "#2563EB";
  if (s === "paid") return colors.success;
  if (s === "rejected") return colors.error;
  return colors.warning;
}

function StatusPill({ status }: { status: string }) {
  const c = statusColor(status);
  const label =
    status === "pending" ? "Pending Approval"
    : status === "approved" ? "Approved"
    : status === "paid" ? "Paid"
    : "Rejected";
  return (
    <View style={[styles.pill, { borderColor: c, backgroundColor: c + "1A" }]}>
      <Txt style={{ color: c, fontWeight: "700", fontSize: 11 }}>{label}</Txt>
    </View>
  );
}

export default function AdminRedemptions() {
  const [items, setItems] = useState<Req[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<string>("pending");
  const [q, setQ] = useState("");

  // Modals
  const [selected, setSelected] = useState<Req | null>(null);
  const [paidOpen, setPaidOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [payRef, setPayRef] = useState("");
  const [payDate, setPayDate] = useState("");
  const [payRemarks, setPayRemarks] = useState("");
  const [rejReason, setRejReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      params.set("status", tab);
      if (q.trim()) params.set("q", q.trim());
      const data = await api<any>(`/admin/redemption-requests?${params.toString()}`);
      setItems(data?.items || []);
      setCounts(data?.counts || {});
    } catch (e: any) {
      Alert.alert("Failed to load", e.message || "Please retry.");
    } finally {
      setRefreshing(false);
    }
  }, [tab, q]);

  useEffect(() => { load(); }, [load]);

  async function approve(r: Req) {
    Alert.alert(
      "Approve redemption?",
      `Approve ${r.credits_requested} credits (₹${r.amount_inr.toFixed(2)}) for ${r.pro_name}?`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Approve",
          style: "default",
          onPress: async () => {
            try {
              await api(`/admin/redemption-requests/${r.id}/approve`, { method: "POST" });
              successAlert.show({ title: "Request Approved", message: "The redemption request status has been updated to Approved." });
              load();
            } catch (e: any) {
              Alert.alert("Failed", e.message || "Could not approve.");
            }
          },
        },
      ],
    );
  }

  function openMarkPaid(r: Req) {
    setSelected(r);
    setPayRef("");
    setPayDate(new Date().toISOString().slice(0, 10));
    setPayRemarks("");
    setPaidOpen(true);
  }

  async function submitPaid() {
    if (!selected) return;
    if (payRef.trim().length < 2) return Alert.alert("Missing details", "Please enter a Transaction Reference Number.");
    setBusy(true);
    try {
      await api(`/admin/redemption-requests/${selected.id}/mark-paid`, {
        method: "POST",
        body: {
          payment_ref: payRef.trim(),
          payment_date: payDate ? new Date(payDate).toISOString() : undefined,
          remarks: payRemarks.trim(),
        },
      });
      setPaidOpen(false);
      successAlert.show({ title: "Marked as Paid", message: "The Working Professional has been notified about the successful payment." });
      load();
    } catch (e: any) {
      Alert.alert("Failed", e.message || "Could not mark as paid.");
    } finally {
      setBusy(false);
    }
  }

  function openReject(r: Req) {
    setSelected(r);
    setRejReason("");
    setRejectOpen(true);
  }

  async function submitReject() {
    if (!selected) return;
    if (rejReason.trim().length < 2) return Alert.alert("Missing reason", "Please provide a rejection reason.");
    setBusy(true);
    try {
      await api(`/admin/redemption-requests/${selected.id}/reject`, {
        method: "POST",
        body: { reason: rejReason.trim() },
      });
      setRejectOpen(false);
      successAlert.show({ title: "Request Rejected", message: "The locked credits have been returned to the Professional's available balance." });
      load();
    } catch (e: any) {
      Alert.alert("Failed", e.message || "Could not reject.");
    } finally {
      setBusy(false);
    }
  }

  const total = useMemo(() => Object.values(counts).reduce((a, b) => a + b, 0), [counts]);

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={styles.headerRow}>
        <View style={{ flex: 1 }}>
          <ScreenTitle
            title="Approvals"
            icon="checkmark-done-circle"
            color={colors.admin || colors.primary}
            subtitle="Credit Redemption Requests"
          />
        </View>
      </View>

      <Input
        testID="redemption-search"
        placeholder="Search by name, email, request ID or UPI…"
        value={q}
        onChangeText={setQ}
      />

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {STATUS_TABS.map((t) => {
          const active = tab === t.key;
          const count = t.key === "all" ? total : (counts[t.key] || 0);
          return (
            <TouchableOpacity
              key={t.key}
              testID={`tab-${t.key}`}
              onPress={() => setTab(t.key)}
              style={[styles.tab, active && styles.tabActive]}
              activeOpacity={0.7}
            >
              <Ionicons name={t.ion} size={14} color={active ? "#fff" : colors.textSecondary} />
              <Txt style={[styles.tabLabel, active && { color: "#fff" }]}>{t.label}</Txt>
              <View style={[styles.countPill, active && { backgroundColor: "rgba(255,255,255,0.25)" }]}>
                <Txt style={[styles.countTxt, active && { color: "#fff" }]}>{count}</Txt>
              </View>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <View style={{ marginTop: 12, gap: 10 }}>
        {items.length === 0 ? (
          <Card style={{ paddingVertical: 24, alignItems: "center" }}>
            <Ionicons name="checkmark-done" size={32} color={colors.success} />
            <Txt variant="muted" style={{ marginTop: 6 }}>No requests in this status.</Txt>
          </Card>
        ) : null}

        {items.map((r) => (
          <Card key={r.id} padding={14}>
            <View style={{ flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" }}>
              <View style={{ flex: 1, paddingRight: 8 }}>
                <Txt style={{ fontWeight: "700" }} numberOfLines={1}>{r.pro_name}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }} numberOfLines={1}>{r.pro_email}</Txt>
                <View style={styles.metaRow}>
                  <Ionicons name="cash" size={14} color={colors.textSecondary} />
                  <Txt variant="small" style={styles.metaTxt}>{r.credits_requested} credits → ₹{r.amount_inr.toFixed(2)}</Txt>
                </View>
                <View style={styles.metaRow}>
                  <Ionicons name="card" size={14} color={colors.textSecondary} />
                  <Txt variant="small" style={styles.metaTxt} numberOfLines={1}>UPI: {r.upi_id}</Txt>
                </View>
                {r.bank_account ? (
                  <View style={styles.metaRow}>
                    <Ionicons name="business" size={14} color={colors.textSecondary} />
                    <Txt variant="small" style={styles.metaTxt} numberOfLines={1}>
                      A/c: {r.bank_account}{r.ifsc ? ` · IFSC ${r.ifsc}` : ""}
                    </Txt>
                  </View>
                ) : null}
                <View style={styles.metaRow}>
                  <Ionicons name="calendar" size={14} color={colors.textSecondary} />
                  <Txt variant="small" style={styles.metaTxt}>
                    {new Date(r.created_at).toLocaleString()}
                  </Txt>
                </View>
                <View style={styles.metaRow}>
                  <Ionicons name="finger-print" size={14} color={colors.textSecondary} />
                  <Txt variant="small" style={styles.metaTxt} numberOfLines={1}>ID: {r.id}</Txt>
                </View>
                {r.status === "paid" && r.payment_ref ? (
                  <Txt variant="small" style={{ color: colors.success, marginTop: 6 }} numberOfLines={2}>
                    ✅ Ref: {r.payment_ref}{r.payment_date ? ` · ${new Date(r.payment_date).toLocaleDateString()}` : ""}
                  </Txt>
                ) : null}
                {r.status === "rejected" && r.rejection_reason ? (
                  <Txt variant="small" style={{ color: colors.error, marginTop: 6 }} numberOfLines={2}>
                    ⚠️ {r.rejection_reason}
                  </Txt>
                ) : null}
              </View>
              <StatusPill status={r.status} />
            </View>

            {/* Action buttons by status */}
            {r.status === "pending" ? (
              <View style={styles.actionsRow}>
                <Button
                  testID={`approve-${r.id}`}
                  title="Approve"
                  variant="primary"
                  icon={<Ionicons name="checkmark" size={16} color="#fff" />}
                  onPress={() => approve(r)}
                  style={{ flex: 1 }}
                />
                <Button
                  testID={`reject-${r.id}`}
                  title="Reject"
                  variant="outline"
                  icon={<Ionicons name="close" size={16} color={colors.error} />}
                  onPress={() => openReject(r)}
                  style={{ flex: 1 }}
                />
              </View>
            ) : null}
            {r.status === "approved" ? (
              <View style={styles.actionsRow}>
                <Button
                  testID={`mark-paid-${r.id}`}
                  title="Mark as Paid"
                  variant="primary"
                  icon={<Ionicons name="wallet" size={16} color="#fff" />}
                  onPress={() => openMarkPaid(r)}
                  style={{ flex: 1 }}
                />
                <Button
                  testID={`reject-${r.id}`}
                  title="Reject"
                  variant="outline"
                  icon={<Ionicons name="close" size={16} color={colors.error} />}
                  onPress={() => openReject(r)}
                  style={{ flex: 1 }}
                />
              </View>
            ) : null}
          </Card>
        ))}
      </View>

      {/* Mark Paid Modal */}
      <Modal visible={paidOpen} transparent animationType="slide" onRequestClose={() => setPaidOpen(false)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <Txt variant="h3">Mark as Paid</Txt>
              <TouchableOpacity onPress={() => setPaidOpen(false)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.textPrimary} />
              </TouchableOpacity>
            </View>
            {selected ? (
              <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>
                {selected.pro_name} · {selected.credits_requested} credits (₹{selected.amount_inr.toFixed(2)})
              </Txt>
            ) : null}
            <Input
              testID="pay-ref"
              label="Transaction Reference Number *"
              placeholder="UPI / Bank txn ref"
              value={payRef}
              onChangeText={setPayRef}
            />
            <Input
              testID="pay-date"
              label="Payment Date (YYYY-MM-DD)"
              value={payDate}
              onChangeText={setPayDate}
              placeholder="2026-06-14"
            />
            <Input
              testID="pay-remarks"
              label="Remarks (Optional)"
              value={payRemarks}
              onChangeText={setPayRemarks}
              multiline
              numberOfLines={3}
            />
            <Button
              testID="submit-paid"
              title="Confirm Payment"
              loading={busy}
              onPress={submitPaid}
              icon={<Ionicons name="checkmark-circle" size={18} color="#fff" />}
            />
          </View>
        </View>
      </Modal>

      {/* Reject Modal */}
      <Modal visible={rejectOpen} transparent animationType="slide" onRequestClose={() => setRejectOpen(false)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <Txt variant="h3">Reject Redemption</Txt>
              <TouchableOpacity onPress={() => setRejectOpen(false)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.textPrimary} />
              </TouchableOpacity>
            </View>
            {selected ? (
              <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>
                {selected.pro_name} · {selected.credits_requested} credits will be returned to the user.
              </Txt>
            ) : null}
            <Input
              testID="rej-reason"
              label="Reason *"
              placeholder="Invalid UPI / Verification Failed / Duplicate Request"
              value={rejReason}
              onChangeText={setRejReason}
              multiline
              numberOfLines={3}
            />
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
              {["Invalid UPI Details", "Verification Failed", "Duplicate Request"].map((reason) => (
                <TouchableOpacity key={reason} onPress={() => setRejReason(reason)} style={styles.quickPill}>
                  <Txt style={{ fontSize: 11, color: colors.textPrimary }}>{reason}</Txt>
                </TouchableOpacity>
              ))}
            </View>
            <Button
              testID="submit-reject"
              title="Reject Request"
              loading={busy}
              variant="outline"
              onPress={submitReject}
              icon={<Ionicons name="close-circle" size={18} color={colors.error} />}
              style={{ marginTop: 10 }}
            />
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "center", marginBottom: 8 },
  tab: {
    flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: colors.surface, borderRadius: 18, paddingHorizontal: 12, paddingVertical: 7,
    borderWidth: 1, borderColor: colors.border,
  },
  tabActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  tabLabel: { fontSize: 12, fontWeight: "600", color: colors.textSecondary },
  countPill: { marginLeft: 4, backgroundColor: colors.border, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 8, minWidth: 20, alignItems: "center" },
  countTxt: { fontSize: 10, fontWeight: "700", color: colors.textPrimary },
  metaRow: { flexDirection: "row", alignItems: "center", marginTop: 4, gap: 6 },
  metaTxt: { color: colors.textSecondary, flexShrink: 1 },
  pill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10, borderWidth: 1, alignSelf: "flex-start" },
  actionsRow: { flexDirection: "row", gap: 8, marginTop: 12 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.bg, padding: 18, borderTopLeftRadius: 20, borderTopRightRadius: 20, gap: 4 },
  quickPill: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 14 },
});
