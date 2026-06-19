import React, { useEffect, useState, useCallback, useMemo } from "react";
import { View, StyleSheet, TouchableOpacity, TextInput, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

const STATUS_FILTERS = [
  { key: "all", label: "All", color: colors.textPrimary },
  { key: "applied", label: "Applied", color: colors.accent },
  { key: "shortlisted", label: "Shortlisted", color: "#2563EB" },
  { key: "referred", label: "Referred", color: "#7C3AED" },
  { key: "interview_scheduled", label: "Interview Scheduled", color: colors.primary },
  { key: "hired", label: "Hired", color: colors.success },
  { key: "rejected", label: "Rejected", color: colors.error },
];

function statusMeta(s: string) {
  return STATUS_FILTERS.find((f) => f.key === s) || { key: s, label: s || "-", color: colors.accent };
}

export default function MyApplications() {
  const router = useRouter();
  const [apps, setApps] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  // Sort by Latest Applied is the default (server already returns DESC). Toggle reverses it.
  const [sortDesc, setSortDesc] = useState(true);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const a = await api<any[]>("/applications");
      setApps(a || []);
    } catch {}
    setRefreshing(false);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    let list = [...apps];
    if (statusFilter !== "all") list = list.filter((a) => a.status === statusFilter);
    const q = query.trim().toLowerCase();
    if (q) {
      list = list.filter((a) =>
        [a.job_title, a.company, a.location, a.referrer_pro_name]
          .filter(Boolean)
          .some((x) => String(x).toLowerCase().includes(q))
      );
    }
    list.sort((a, b) => {
      const ta = new Date(a.created_at || 0).getTime();
      const tb = new Date(b.created_at || 0).getTime();
      return sortDesc ? tb - ta : ta - tb;
    });
    return list;
  }, [apps, query, statusFilter, sortDesc]);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={["top"]}>
      <View style={styles.header}>
        <TouchableOpacity testID="back-btn" onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="chevron-back" size={28} color={colors.textPrimary} />
        </TouchableOpacity>
        <Txt variant="h3">My Job Applications</Txt>
        <View style={{ width: 28 }} />
      </View>

      <View style={styles.searchRow}>
        <View style={styles.searchBox}>
          <Ionicons name="search" size={18} color={colors.textSecondary} />
          <TextInput
            testID="apps-search"
            value={query}
            onChangeText={setQuery}
            placeholder="Search by job, company, location"
            placeholderTextColor={colors.textSecondary}
            style={styles.searchInput}
          />
          {query ? (
            <TouchableOpacity onPress={() => setQuery("")} hitSlop={8}>
              <Ionicons name="close-circle" size={18} color={colors.textSecondary} />
            </TouchableOpacity>
          ) : null}
        </View>
        <TouchableOpacity
          testID="apps-sort"
          onPress={() => setSortDesc((v) => !v)}
          style={styles.sortBtn}
        >
          <Ionicons name={sortDesc ? "arrow-down" : "arrow-up"} size={16} color={colors.textPrimary} />
          <Txt variant="small" style={{ fontWeight: "700", marginLeft: 4 }}>{sortDesc ? "Latest" : "Oldest"}</Txt>
        </TouchableOpacity>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
        {STATUS_FILTERS.map((f) => {
          const active = statusFilter === f.key;
          return (
            <TouchableOpacity
              key={f.key}
              testID={`status-${f.key}`}
              onPress={() => setStatusFilter(f.key)}
              style={[styles.chip, active && { backgroundColor: f.color, borderColor: f.color }]}
            >
              <Txt variant="small" style={{ fontWeight: "700", color: active ? "#fff" : f.color }}>
                {f.label}
              </Txt>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <Screen refreshing={refreshing} onRefresh={load} noPad>
        <View style={{ padding: 20, paddingTop: 4, gap: 10 }}>
          {!loading && filtered.length === 0 ? (
            <Card>
              <Txt variant="muted">No applications match. Adjust your search or filters.</Txt>
            </Card>
          ) : null}
          {filtered.map((a) => {
            const meta = statusMeta(a.status);
            return (
              <TouchableOpacity
                key={a.id}
                testID={`app-${a.id}`}
                onPress={() => router.push(`/student/applications/${a.id}`)}
                activeOpacity={0.85}
              >
                <Card>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <View style={{ flex: 1, marginRight: 8 }}>
                      <Txt variant="h3" numberOfLines={1}>{a.job_title || "—"}</Txt>
                      {a.company ? (
                        <View style={styles.metaRow}>
                          <Ionicons name="business" size={13} color={colors.textSecondary} />
                          <Txt variant="small" style={styles.metaText} numberOfLines={1}>{a.company}</Txt>
                        </View>
                      ) : null}
                      {a.location ? (
                        <View style={styles.metaRow}>
                          <Ionicons name="location-sharp" size={13} color={colors.textSecondary} />
                          <Txt variant="small" style={styles.metaText} numberOfLines={1}>{a.location}</Txt>
                        </View>
                      ) : null}
                      <View style={styles.metaRow}>
                        <Ionicons name="calendar" size={13} color={colors.textSecondary} />
                        <Txt variant="small" style={styles.metaText}>
                          Applied {new Date(a.created_at).toLocaleDateString()}
                        </Txt>
                      </View>
                      {a.referrer_pro_name ? (
                        <View style={styles.metaRow}>
                          <Ionicons name="people" size={13} color={"#7C3AED"} />
                          <Txt variant="small" style={[styles.metaText, { color: "#7C3AED" }]}>
                            Referred by {a.referrer_pro_name}
                          </Txt>
                        </View>
                      ) : null}
                    </View>
                    <View style={[styles.pill, { backgroundColor: meta.color }]}>
                      <Txt variant="small" style={{ color: "#fff", fontWeight: "700" }}>
                        {meta.label}
                      </Txt>
                    </View>
                  </View>
                </Card>
              </TouchableOpacity>
            );
          })}
        </View>
      </Screen>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border },
  searchRow: { flexDirection: "row", paddingHorizontal: 20, paddingTop: 12, gap: 8 },
  searchBox: { flex: 1, flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceAlt, borderRadius: radius.lg, paddingHorizontal: 12, height: 42, gap: 8 },
  searchInput: { flex: 1, color: colors.textPrimary, fontSize: 14, paddingVertical: 0 },
  sortBtn: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, height: 42, backgroundColor: colors.surfaceAlt, borderRadius: radius.lg },
  chipRow: { paddingHorizontal: 20, paddingVertical: 10, gap: 8 },
  chip: { borderWidth: 1, borderColor: colors.border, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: colors.surface },
  pill: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 12 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  metaText: { color: colors.textSecondary, flexShrink: 1 },
});
