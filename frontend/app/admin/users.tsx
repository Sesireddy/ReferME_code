import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, FlatList, Modal, Alert } from "react-native";
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
import { LOCATION_OPTIONS } from "@/src/lib/constants";
import { successAlert } from "@/src/lib/successAlert";

const ROLE_OPTS = [
  { value: "student", label: "Job Seeker" },
  { value: "professional", label: "Working Professional" },
  { value: "employer", label: "Employer" },
  { value: "admin", label: "Admin" },
];

const STATUS_OPTS = [
  { value: "active", label: "Active" },
  { value: "suspended", label: "Suspended" },
];

const USER_TYPE_OPTS = [
  { value: "", label: "All" },
  { value: "student", label: "Job Seeker" },
  { value: "professional", label: "Working Professional" },
  { value: "employer", label: "Employer" },
];
const PROFILE_STATUS_OPTS = [
  { value: "", label: "All" },
  { value: "active", label: "Active (complete)" },
  { value: "inactive", label: "Inactive (incomplete)" },
  { value: "suspended", label: "Suspended" },
];
const VERIFIED_OPTS = [
  { value: "", label: "All" },
  { value: "verified", label: "Verified" },
  { value: "not_verified", label: "Not Verified" },
];
const REG_RANGE_OPTS = [
  { value: "", label: "All time" },
  { value: "today", label: "Today" },
  { value: "last_7", label: "Last 7 Days" },
  { value: "last_30", label: "Last 30 Days" },
  { value: "custom", label: "Custom Date Range" },
];

export default function AdminUsers() {
  const [items, setItems] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  const [q, setQ] = useState("");
  const [userType, setUserType] = useState<string | null>("");
  const [location, setLocation] = useState<string | null>("");
  const [profileStatus, setProfileStatus] = useState<string | null>("");
  const [emailVer, setEmailVer] = useState<string | null>("");
  const [mobileVer, setMobileVer] = useState<string | null>("");

  // Edit Modal state
  const [editing, setEditing] = useState<any | null>(null);
  const [editName, setEditName] = useState("");
  const [editRole, setEditRole] = useState<string | null>(null);
  const [editStatus, setEditStatus] = useState<string | null>(null);
  const [editReason, setEditReason] = useState("");

  // Credit Adjust Modal state
  const [adjusting, setAdjusting] = useState<any | null>(null);
  const [adjDelta, setAdjDelta] = useState("");
  const [adjReason, setAdjReason] = useState("");

  const [busy, setBusy] = useState(false);

  const openEdit = (u: any) => {
    setEditing(u);
    setEditName(u.name || "");
    setEditRole(u.role);
    setEditStatus(u.account_status || "active");
    setEditReason("");
  };

  const openAdjust = (u: any) => {
    setAdjusting(u);
    setAdjDelta("");
    setAdjReason("");
  };

  const submitEdit = async () => {
    if (!editing) return;
    setBusy(true);
    try {
      await api(`/admin/users/${editing.id}`, {
        method: "PATCH",
        body: {
          name: editName,
          role: editRole,
          account_status: editStatus,
          reason: editReason,
        },
      });
      setEditing(null);
      successAlert.show({ title: "User Updated", message: `Changes saved for ${editName || editing.email}.` });
      load();
    } catch (e: any) {
      Alert.alert("Failed", e.message || "Could not save changes.");
    } finally {
      setBusy(false);
    }
  };

  const submitAdjust = async () => {
    if (!adjusting) return;
    const delta = parseInt(adjDelta, 10);
    if (!delta) return Alert.alert("Invalid amount", "Enter a non-zero integer (negative to deduct).");
    if (adjReason.trim().length < 2) return Alert.alert("Reason required", "Please add a short reason for the audit log.");
    setBusy(true);
    try {
      const r = await api<any>(`/admin/users/${adjusting.id}/credits/adjust`, {
        method: "POST",
        body: { delta, reason: adjReason.trim() },
      });
      setAdjusting(null);
      successAlert.show({
        title: "Credits Adjusted",
        message: `${delta > 0 ? "Added" : "Deducted"} ${Math.abs(delta)} credits. New balance: ${r.credits}.`,
      });
      load();
    } catch (e: any) {
      Alert.alert("Failed", e.message || "Could not adjust credits.");
    } finally {
      setBusy(false);
    }
  };
  const [regRange, setRegRange] = useState<string | null>("");
  const [regFrom, setRegFrom] = useState("");
  const [regTo, setRegTo] = useState("");

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.set("q", q.trim());
      if (userType) params.set("user_type", userType);
      if (location) params.set("location", location);
      if (profileStatus) params.set("profile_status", profileStatus);
      if (emailVer) params.set("email_verified", emailVer);
      if (mobileVer) params.set("mobile_verified", mobileVer);
      if (regRange) params.set("registration_range", regRange);
      if (regRange === "custom" && regFrom) params.set("registration_from", regFrom);
      if (regRange === "custom" && regTo) params.set("registration_to", regTo);
      const data = await api<any[]>(`/admin/users/search${params.toString() ? "?" + params.toString() : ""}`);
      setItems(data);
    } catch {}
    setRefreshing(false);
  }, [q, userType, location, profileStatus, emailVer, mobileVer, regRange, regFrom, regTo]);

  useEffect(() => { load(); }, []);

  function reset() {
    setQ(""); setUserType(""); setLocation(""); setProfileStatus(""); setEmailVer(""); setMobileVer("");
    setRegRange(""); setRegFrom(""); setRegTo("");
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <ScreenTitle title="Users" icon="people" color={colors.primary} />
        </View>
        <TouchableOpacity testID="toggle-filters" onPress={() => setShowFilters(p => !p)} style={styles.btn}>
          <Ionicons name="options" size={20} color={colors.textPrimary} />
        </TouchableOpacity>
      </View>
      <Input
        testID="user-search"
        value={q}
        onChangeText={setQ}
        placeholder="Search ID / name / mobile / email / company / skill…"
        autoCapitalize="none"
        autoCorrect={false}
        style={{ marginTop: 8 }}
      />
      <View style={{ flexDirection: "row", gap: 10, marginTop: 4 }}>
        <Button testID="search-apply" title="Search" onPress={load} style={{ flex: 1 }} />
        <Button testID="search-clear" title="Reset" variant="outline" onPress={() => { reset(); load(); }} style={{ flex: 1 }} />
      </View>

      {showFilters ? (
        <Card style={{ marginTop: 12 }}>
          <Picker label="User Type" options={USER_TYPE_OPTS} value={userType} onChange={(v) => setUserType(v as string)} placeholder="All" />
          <Picker label="Location" options={[{ value: "", label: "All" }, ...LOCATION_OPTIONS]} value={location} onChange={(v) => setLocation(v as string)} placeholder="All" />
          <Picker label="Profile Status" options={PROFILE_STATUS_OPTS} value={profileStatus} onChange={(v) => setProfileStatus(v as string)} placeholder="All" />
          <Picker label="Mobile Verification" options={VERIFIED_OPTS} value={mobileVer} onChange={(v) => setMobileVer(v as string)} placeholder="All" />
          <Picker label="Email Verification" options={VERIFIED_OPTS} value={emailVer} onChange={(v) => setEmailVer(v as string)} placeholder="All" />
          <Picker label="Registration Date" options={REG_RANGE_OPTS} value={regRange} onChange={(v) => setRegRange(v as string)} placeholder="All time" />
          {regRange === "custom" ? (
            <View style={{ flexDirection: "row", gap: 10 }}>
              <View style={{ flex: 1 }}><Input label="From (YYYY-MM-DD)" value={regFrom} onChangeText={setRegFrom} /></View>
              <View style={{ flex: 1 }}><Input label="To (YYYY-MM-DD)" value={regTo} onChangeText={setRegTo} /></View>
            </View>
          ) : null}
          <View style={{ flexDirection: "row", gap: 10, marginTop: 4 }}>
            <Button testID="apply-filter" title="Apply Filter" onPress={() => { load(); setShowFilters(false); }} style={{ flex: 1 }} />
            <Button testID="reset-filter" title="Reset Filter" variant="outline" onPress={() => { reset(); load(); }} style={{ flex: 1 }} />
          </View>
        </Card>
      ) : null}

      <Txt variant="small" style={{ marginTop: 12, color: colors.textSecondary }}>{items.length} result(s)</Txt>
      <FlatList
        data={items}
        scrollEnabled={false}
        keyExtractor={(u) => u.id}
        renderItem={({ item: u }) => (
          <Card style={{ marginTop: 10 }} padding={14}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <View style={{ flex: 1 }}>
                <Txt variant="h3">{u.name || u.email.split("@")[0]}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }} numberOfLines={1}>{u.email}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                  {u.credits ?? 0} credits · {u.is_email_verified ? "email ✓" : "email ✗"} · {u.profile?.phone_verified ? "mobile ✓" : "mobile ✗"} · {(u.account_status || "active")}
                </Txt>
              </View>
              <View style={[styles.pill, { backgroundColor: roleColor(u.role) }]}>
                <Txt variant="small" style={{ color: "#fff", fontWeight: "700", textTransform: "capitalize" }}>{u.role}</Txt>
              </View>
            </View>
            <View style={{ flexDirection: "row", gap: 8, marginTop: 10 }}>
              <Button
                testID={`edit-user-${u.id}`}
                title="Edit"
                variant="outline"
                onPress={() => openEdit(u)}
                style={{ flex: 1 }}
                icon={<Ionicons name="create-outline" size={16} color={colors.primary} />}
              />
              <Button
                testID={`adjust-credits-${u.id}`}
                title="Adjust Credits"
                variant="outline"
                onPress={() => openAdjust(u)}
                style={{ flex: 1 }}
                icon={<Ionicons name="cash-outline" size={16} color={colors.success} />}
              />
            </View>
          </Card>
        )}
        ListEmptyComponent={<Txt variant="muted" style={{ marginTop: 16 }}>No users match the selected filters.</Txt>}
      />

      {/* Edit User Modal */}
      <Modal visible={!!editing} transparent animationType="slide" onRequestClose={() => setEditing(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Txt variant="h3">Edit User</Txt>
              <TouchableOpacity onPress={() => setEditing(null)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.textPrimary} />
              </TouchableOpacity>
            </View>
            {editing ? (
              <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>{editing.email}</Txt>
            ) : null}
            <Input testID="edit-name" label="Name" value={editName} onChangeText={setEditName} />
            <Picker testID="edit-role" label="Role" options={ROLE_OPTS} value={editRole} onChange={(v) => setEditRole(v as string)} />
            <Picker testID="edit-status" label="Account Status" options={STATUS_OPTS} value={editStatus} onChange={(v) => setEditStatus(v as string)} />
            <Input testID="edit-reason" label="Reason (for audit log)" value={editReason} onChangeText={setEditReason} multiline numberOfLines={2} />
            <Button testID="edit-submit" title="Save Changes" loading={busy} onPress={submitEdit} icon={<Ionicons name="checkmark" size={18} color="#fff" />} />
          </View>
        </View>
      </Modal>

      {/* Adjust Credits Modal */}
      <Modal visible={!!adjusting} transparent animationType="slide" onRequestClose={() => setAdjusting(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Txt variant="h3">Adjust Credits</Txt>
              <TouchableOpacity onPress={() => setAdjusting(null)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.textPrimary} />
              </TouchableOpacity>
            </View>
            {adjusting ? (
              <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>
                {adjusting.email} · current balance: {adjusting.credits ?? 0}
              </Txt>
            ) : null}
            <Input
              testID="adj-delta"
              label="Delta (positive to add, negative to deduct)"
              placeholder="e.g. 100 or -50"
              keyboardType="numbers-and-punctuation"
              value={adjDelta}
              onChangeText={(t) => setAdjDelta(t.replace(/[^0-9\-]/g, ""))}
            />
            <Input testID="adj-reason" label="Reason (required)" value={adjReason} onChangeText={setAdjReason} multiline numberOfLines={2} />
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
              {["Goodwill credit", "Refund for technical issue", "Manual deposit", "Penalty deduction"].map((q) => (
                <TouchableOpacity key={q} onPress={() => setAdjReason(q)} style={styles.quickPill}>
                  <Txt style={{ fontSize: 11, color: colors.textPrimary }}>{q}</Txt>
                </TouchableOpacity>
              ))}
            </View>
            <Button testID="adj-submit" title="Apply Adjustment" loading={busy} onPress={submitAdjust} icon={<Ionicons name="cash" size={18} color="#fff" />} style={{ marginTop: 10 }} />
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

function roleColor(r: string) {
  if (r === "student") return colors.primary;
  if (r === "professional") return "#7C3AED";
  if (r === "employer") return "#2563EB";
  return "#0F172A";
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  btn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  pill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.bg, padding: 18, borderTopLeftRadius: 20, borderTopRightRadius: 20 },
  quickPill: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 14 },
});
