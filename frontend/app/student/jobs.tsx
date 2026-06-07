import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { Picker } from "@/src/components/Picker";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

type Tab = "jobs" | "applications";

const CAT_OPTS = [
  { value: "", label: "All" },
  { value: "fresher", label: "Fresher" },
  { value: "experienced", label: "Experienced" },
];

export default function StudentJobs() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("jobs");
  const [jobs, setJobs] = useState<any[]>([]);
  const [apps, setApps] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  // Filters
  const [skill, setSkill] = useState("");
  const [location, setLocation] = useState("");
  const [category, setCategory] = useState<string | null>("");
  const [expMin, setExpMin] = useState("");
  const [expMax, setExpMax] = useState("");
  const [company, setCompany] = useState("");

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (skill) params.set("skill", skill);
      if (location) params.set("location", location);
      if (category) params.set("category", category);
      if (expMin) params.set("exp_min", expMin);
      if (expMax) params.set("exp_max", expMax);
      if (company) params.set("company", company);
      const qs = params.toString();
      const [j, a] = await Promise.all([
        api<any[]>(`/jobs${qs ? "?" + qs : ""}`),
        api<any[]>("/applications"),
      ]);
      setJobs(j);
      setApps(a);
    } catch {}
    setRefreshing(false);
  }, [skill, location, category, expMin, expMax, company]);

  useEffect(() => {
    load();
  }, [load]);

  async function apply(jobId: string) {
    try {
      const r = await api<{ used_free?: boolean }>("/jobs/apply", { method: "POST", body: { job_id: jobId } });
      Alert.alert("Applied", r.used_free ? "Used a free token!" : "49 credits spent.");
      load();
    } catch (e: any) {
      const msg = e.message || "";
      if (/insufficient credit/i.test(msg)) {
        Alert.alert(
          "Insufficient credits",
          "Please add credits to continue applying for this job.",
          [
            { text: "Add Credits", onPress: () => router.push("/student/wallet") },
            { text: "Cancel", style: "cancel" },
          ],
        );
      } else {
        Alert.alert("Cannot apply", msg);
      }
    }
  }

  function clearFilters() {
    setSkill(""); setLocation(""); setCategory(""); setExpMin(""); setExpMax(""); setCompany("");
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <Txt variant="h1">Jobs</Txt>
        <TouchableOpacity testID="filter-btn" onPress={() => setShowFilters((p) => !p)} style={styles.filterBtn}>
          <Ionicons name="options" size={20} color={colors.textPrimary} />
        </TouchableOpacity>
      </View>

      <View style={styles.tabs}>
        {(["jobs", "applications"] as Tab[]).map((t) => (
          <TouchableOpacity key={t} testID={`tab-${t}`} onPress={() => setTab(t)} style={[styles.tab, tab === t && styles.tabActive]}>
            <Txt style={{ fontWeight: "700", color: tab === t ? "#fff" : colors.textPrimary, textTransform: "capitalize" }}>{t}</Txt>
          </TouchableOpacity>
        ))}
      </View>

      {showFilters && tab === "jobs" ? (
        <Card style={{ marginTop: 12 }}>
          <Input testID="f-skill" label="Skill" value={skill} onChangeText={setSkill} placeholder="React, Python" />
          <Input testID="f-location" label="Location" value={location} onChangeText={setLocation} placeholder="Bengaluru / Remote" />
          <Picker testID="f-cat" label="Category" options={CAT_OPTS} value={category} onChange={(v) => setCategory(v as string)} placeholder="All" />
          <View style={{ flexDirection: "row", gap: 8 }}>
            <View style={{ flex: 1 }}><Input testID="f-expmin" label="Min exp (years)" value={expMin} onChangeText={setExpMin} keyboardType="number-pad" /></View>
            <View style={{ flex: 1 }}><Input testID="f-expmax" label="Max exp" value={expMax} onChangeText={setExpMax} keyboardType="number-pad" /></View>
          </View>
          <Input testID="f-company" label="Company" value={company} onChangeText={setCompany} placeholder="Acme" />
          <TouchableOpacity testID="f-clear" onPress={clearFilters} style={{ alignSelf: "flex-end" }}>
            <Txt style={{ color: colors.primary, fontWeight: "700" }}>Clear filters</Txt>
          </TouchableOpacity>
        </Card>
      ) : null}

      {tab === "jobs" ? (
        <View style={{ gap: 12, marginTop: 16 }}>
          {jobs.length === 0 ? <Txt variant="muted">No jobs match — try adjusting filters.</Txt> : null}
          {jobs.map((j) => (
            <Card key={j.id}>
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                <View style={{ flex: 1 }}>
                  <Txt variant="h3">{j.title}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                    {j.company || j.employer_name} · {j.location || "Anywhere"} · {j.salary_range || ""}
                  </Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2, textTransform: "capitalize" }}>
                    {j.category || "fresher"}{j.experience_required ? ` · ${j.experience_required}y+` : ""}
                  </Txt>
                </View>
                {(j.open_positions || j.bulk_openings) > 1 ? (
                  <View style={styles.badge}>
                    <Txt variant="small" style={{ fontWeight: "700", color: colors.primary }}>{j.open_positions || j.bulk_openings} openings</Txt>
                  </View>
                ) : null}
              </View>
              <Txt variant="small" style={{ marginTop: 8, color: colors.textSecondary }} numberOfLines={2}>{j.description}</Txt>
              {j.skills_required?.length ? (
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                  {j.skills_required.slice(0, 5).map((s: string) => (
                    <View key={s} style={styles.chip}><Txt variant="small">{s}</Txt></View>
                  ))}
                </View>
              ) : null}
              {j.applied ? (
                <View style={[styles.appliedPill, { marginTop: 12 }]}>
                  <Ionicons name="checkmark-circle" size={18} color={colors.success} />
                  <Txt style={{ color: colors.success, fontWeight: "700", marginLeft: 6, textTransform: "capitalize" }}>
                    {j.application_status || "Applied"}
                  </Txt>
                </View>
              ) : (
                <Button testID={`apply-${j.id}`} title="Apply" onPress={() => apply(j.id)} style={{ marginTop: 12 }} />
              )}
            </Card>
          ))}
        </View>
      ) : null}

      {tab === "applications" ? (
        <View style={{ gap: 12, marginTop: 16 }}>
          {apps.length === 0 ? <Txt variant="muted">No applications yet.</Txt> : null}
          {apps.map((a) => (
            <Card key={a.id}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <View style={{ flex: 1 }}>
                  <Txt variant="h3">{a.job_title}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                    {a.referrer_pro_name ? `Referred by ${a.referrer_pro_name}` : "Direct"}
                  </Txt>
                </View>
                <View style={[styles.statusPill, { backgroundColor: statusColor(a.status) }]}>
                  <Txt variant="small" style={{ color: "#fff", fontWeight: "700", textTransform: "capitalize" }}>
                    {(a.status || "").replace(/_/g, " ")}
                  </Txt>
                </View>
              </View>
            </Card>
          ))}
        </View>
      ) : null}
    </Screen>
  );
}

function statusColor(s: string) {
  if (s === "hired") return colors.success;
  if (s === "rejected") return colors.error;
  if (s === "referred") return "#7C3AED";
  if (s === "interview_scheduled") return colors.primary;
  if (s === "awaiting_interview") return colors.warning;
  if (s === "shortlisted") return "#2563EB";
  return colors.accent;
}

const styles = StyleSheet.create({
  filterBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  tabs: { flexDirection: "row", marginTop: 16, backgroundColor: colors.surfaceAlt, borderRadius: 999, padding: 4 },
  tab: { flex: 1, paddingVertical: 10, alignItems: "center", borderRadius: 999 },
  tabActive: { backgroundColor: colors.primary },
  badge: { backgroundColor: "#FFE4E5", paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  chip: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  appliedPill: { flexDirection: "row", alignItems: "center", backgroundColor: "#E6F9F0", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 999, alignSelf: "flex-start" },
  statusPill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 },
});
