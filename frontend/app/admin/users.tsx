import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, FlatList } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { Picker } from "@/src/components/Picker";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { LOCATION_OPTIONS } from "@/src/lib/constants";

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
        <Txt variant="h1">Users</Txt>
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
                  {u.credits ?? 0} credits · {u.is_email_verified ? "email ✓" : "email ✗"} · {u.profile?.phone_verified ? "mobile ✓" : "mobile ✗"}
                </Txt>
              </View>
              <View style={[styles.pill, { backgroundColor: roleColor(u.role) }]}>
                <Txt variant="small" style={{ color: "#fff", fontWeight: "700", textTransform: "capitalize" }}>{u.role}</Txt>
              </View>
            </View>
          </Card>
        )}
        ListEmptyComponent={<Txt variant="muted" style={{ marginTop: 16 }}>No users match the selected filters.</Txt>}
      />
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
});
