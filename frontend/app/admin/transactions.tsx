import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, FlatList } from "react-native";
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

const USER_TYPE_OPTS = [
  { value: "", label: "All" },
  { value: "student", label: "Job Seeker" },
  { value: "professional", label: "Professional" },
  { value: "employer", label: "Employer" },
];
const TYPE_OPTS = [
  { value: "", label: "All" },
  { value: "purchase", label: "Credit Purchase" },
  { value: "application", label: "Job Application" },
  { value: "interview_reward", label: "Mock Interview Reward" },
  { value: "job_post_reward", label: "Job Posting Reward" },
  { value: "hiring_reward", label: "Hiring Reward" },
  { value: "manual", label: "Manual Adjustment" },
];

export default function AdminTransactions() {
  const [items, setItems] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [q, setQ] = useState("");
  const [userType, setUserType] = useState<string | null>("");
  const [type, setType] = useState<string | null>("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.set("q", q.trim());
      if (userType) params.set("user_type", userType);
      if (type) params.set("type", type);
      if (from) params.set("date_from", from);
      if (to) params.set("date_to", to);
      const data = await api<any[]>(`/admin/transactions/search${params.toString() ? "?" + params.toString() : ""}`);
      setItems(data);
    } catch {}
    setRefreshing(false);
  }, [q, userType, type, from, to]);

  useEffect(() => { load(); }, []);

  function reset() { setQ(""); setUserType(""); setType(""); setFrom(""); setTo(""); }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <ScreenTitle title="Credits" icon="cash" color={colors.primary} />
        </View>
        <TouchableOpacity onPress={() => setShowFilters(p => !p)} style={styles.btn}>
          <Ionicons name="options" size={20} color={colors.textPrimary} />
        </TouchableOpacity>
      </View>
      <Input value={q} onChangeText={setQ} placeholder="Search by transaction ID / name / email" style={{ marginTop: 8 }} />

      {showFilters ? (
        <Card style={{ marginTop: 8 }}>
          <Picker label="User Type" options={USER_TYPE_OPTS} value={userType} onChange={(v) => setUserType(v as string)} placeholder="All" />
          <Picker label="Transaction Type" options={TYPE_OPTS} value={type} onChange={(v) => setType(v as string)} placeholder="All" />
          <Input label="From (YYYY-MM-DD)" value={from} onChangeText={setFrom} />
          <Input label="To (YYYY-MM-DD)" value={to} onChangeText={setTo} />
          <View style={{ flexDirection: "row", gap: 10, marginTop: 4 }}>
            <Button title="Apply Filter" onPress={() => { load(); setShowFilters(false); }} style={{ flex: 1 }} />
            <Button title="Reset" variant="outline" onPress={() => { reset(); load(); }} style={{ flex: 1 }} />
          </View>
        </Card>
      ) : null}

      <Txt variant="small" style={{ marginTop: 12, color: colors.textSecondary }}>{items.length} result(s)</Txt>
      <FlatList
        data={items}
        keyExtractor={(t) => t.id}
        scrollEnabled={false}
        renderItem={({ item: t }) => {
          const credit = t.credits_added > 0;
          return (
            <Card style={{ marginTop: 10 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                <View style={{ flex: 1 }}>
                  <Txt variant="h3">{t.user_name || "—"}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary }}>{t.user_email || "—"} • {t.user_type || "—"}</Txt>
                  <Txt variant="small" style={{ marginTop: 4, color: colors.textSecondary }}>{(t.reason || "").replace(/_/g, " ")}</Txt>
                  <Txt variant="small" style={{ marginTop: 2, color: colors.textSecondary }}>{new Date(t.created_at).toLocaleString()}</Txt>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Txt variant="h3" style={{ color: credit ? colors.success : colors.error }}>
                    {credit ? `+${t.credits_added}` : `-${t.credits_deducted}`}
                  </Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary }}>credits</Txt>
                </View>
              </View>
            </Card>
          );
        }}
        ListEmptyComponent={<Txt variant="muted" style={{ marginTop: 16 }}>No transactions found.</Txt>}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  btn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
});
