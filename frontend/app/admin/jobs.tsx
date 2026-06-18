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
import { ExportMenu } from "@/src/components/ExportMenu";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { LOCATION_OPTIONS, INDUSTRY_OPTIONS, SALARY_RANGE_OPTIONS, JOB_CATEGORY_FILTER_OPTIONS } from "@/src/lib/constants";

export default function AdminJobs() {
  const [items, setItems] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [q, setQ] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState<string | null>("");
  const [category, setCategory] = useState<string | null>("");
  const [industry, setIndustry] = useState<string | null>("");
  const [salary, setSalary] = useState<string | null>("");
  const [postedDate, setPostedDate] = useState("");
  const [status, setStatus] = useState<string | null>("");

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.set("q", q.trim());
      if (company.trim()) params.set("company", company.trim());
      if (location) params.set("location", location);
      if (category) params.set("category", category);
      if (industry) params.set("industry", industry);
      if (salary) params.set("salary_range", salary);
      if (postedDate) params.set("posted_date", postedDate);
      if (status) params.set("status", status);
      const data = await api<any[]>(`/admin/jobs/search${params.toString() ? "?" + params.toString() : ""}`);
      setItems(data);
    } catch {}
    setRefreshing(false);
  }, [q, company, location, category, industry, salary, postedDate, status]);

  useEffect(() => { load(); }, []);

  function reset() {
    setQ(""); setCompany(""); setLocation(""); setCategory(""); setIndustry(""); setSalary(""); setPostedDate(""); setStatus("");
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <ScreenTitle title="Jobs" icon="briefcase" color={colors.primary} />
        </View>
        <ExportMenu entity="jobs" label="Export Jobs" />
        <View style={{ width: 8 }} />
        <TouchableOpacity testID="filter-toggle" onPress={() => setShowFilters(p => !p)} style={styles.btn}>
          <Ionicons name="options" size={20} color={colors.textPrimary} />
        </TouchableOpacity>
      </View>
      <Input testID="search" value={q} onChangeText={setQ} placeholder="Search by ID / Title / Company" style={{ marginTop: 8 }} />

      {showFilters ? (
        <Card style={{ marginTop: 8 }}>
          <Input label="Company" value={company} onChangeText={setCompany} placeholder="e.g. Acme" />
          <Picker label="Location" options={[{ value: "", label: "All" }, ...LOCATION_OPTIONS]} value={location} onChange={(v) => setLocation(v as string)} placeholder="All" />
          <Picker label="Category" options={JOB_CATEGORY_FILTER_OPTIONS} value={category} onChange={(v) => setCategory(v as string)} placeholder="All" />
          <Picker label="Industry Type" options={[{ value: "", label: "All" }, ...INDUSTRY_OPTIONS]} value={industry} onChange={(v) => setIndustry(v as string)} placeholder="All" />
          <Picker label="Salary Range" options={[{ value: "", label: "All" }, ...SALARY_RANGE_OPTIONS]} value={salary} onChange={(v) => setSalary(v as string)} placeholder="All" />
          <Picker label="Status" options={[{ value: "", label: "All" }, { value: "open", label: "Open" }, { value: "closed", label: "Closed" }]} value={status} onChange={(v) => setStatus(v as string)} placeholder="All" />
          <Input label="Posted Date (YYYY-MM-DD)" value={postedDate} onChangeText={setPostedDate} placeholder="2026-06-13" />
          <View style={{ flexDirection: "row", gap: 10, marginTop: 4 }}>
            <Button testID="apply" title="Apply Filter" onPress={() => { load(); setShowFilters(false); }} style={{ flex: 1 }} />
            <Button testID="reset" title="Reset" variant="outline" onPress={() => { reset(); load(); }} style={{ flex: 1 }} />
          </View>
        </Card>
      ) : null}

      <Txt variant="small" style={{ marginTop: 12, color: colors.textSecondary }}>{items.length} result(s)</Txt>
      <FlatList
        data={items}
        keyExtractor={(j) => j.id}
        scrollEnabled={false}
        renderItem={({ item: j }) => (
          <Card style={{ marginTop: 10 }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <View style={{ flex: 1 }}>
                <Txt variant="h3" numberOfLines={1}>{j.title}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>{j.company || "—"} • {j.location || "—"}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>ID: {j.id?.slice(0, 8)} • {new Date(j.created_at).toLocaleDateString()}</Txt>
                <View style={{ flexDirection: "row", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
                  <Chip label={j.category || "—"} />
                  <Chip label={`Openings: ${j.open_positions_label || j.open_positions || "—"}`} />
                  <Chip label={`Applied: ${j.applied_count ?? 0}`} />
                  <Chip label={`Shortlisted: ${j.shortlisted_count ?? 0}`} />
                </View>
              </View>
              <View style={[styles.statusPill, { backgroundColor: j.status === "open" ? colors.success : colors.textSecondary }]}>
                <Txt style={{ color: "#fff", fontWeight: "700", fontSize: 11, textTransform: "capitalize" }}>{j.status || "open"}</Txt>
              </View>
            </View>
          </Card>
        )}
        ListEmptyComponent={<Txt variant="muted" style={{ marginTop: 16 }}>No jobs found matching the selected filters.</Txt>}
      />
    </Screen>
  );
}

function Chip({ label }: { label: string }) {
  return <View style={styles.chip}><Txt variant="small">{label}</Txt></View>;
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  btn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  chip: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  statusPill: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 12, alignSelf: "flex-start" },
});
