import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Picker } from "@/src/components/Picker";
import { Avatar } from "@/src/components/Avatar";
import { ConfirmDialog } from "@/src/components/ConfirmDialog";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import {
  LOCATION_OPTIONS,
  EXP_FILTER_OPTIONS,
  JOB_SORT_OPTIONS,
  JOB_CATEGORY_FILTER_OPTIONS,
  SALARY_RANGE_OPTIONS,
} from "@/src/lib/constants";

type Tab = "jobs" | "applications";

// Helpers for job-card display values --------------------------------------
function salaryLabelOf(j: any): string {
  if (j.salary_range_label) {
    const found = SALARY_RANGE_OPTIONS.find((o) => o.value === j.salary_range_label);
    return found?.label || j.salary_range_label;
  }
  return (j.salary_range || "").trim() || "—";
}
function experienceLabelOf(j: any): string {
  const a = j.experience_min;
  const b = j.experience_max;
  if (a === null || a === undefined) {
    if (j.experience_required) return `${j.experience_required} Year${j.experience_required > 1 ? "s" : ""}`;
    return "—";
  }
  if (a === b || b === null || b === undefined) return `${a} Year${a > 1 ? "s" : ""}`;
  return `${a} – ${b} Years`;
}
function openingsLabelOf(j: any): string {
  if (j.open_positions_label) return j.open_positions_label;
  if (j.open_positions) return String(j.open_positions);
  return "—";
}
function categoryLabelOf(j: any): string {
  const c = (j.category || "").toString();
  if (c === "fresher") return "Fresher";
  if (c === "experienced") return "Experienced";
  if (c === "intern") return "Intern";
  return c || "—";
}

// Reusable icon row used inside job cards
function MetaRow({ icon, label, color }: { icon: keyof typeof Ionicons.glyphMap; label: string; color?: string }) {
  return (
    <View style={styles.metaRow}>
      <Ionicons name={icon} size={14} color={color || colors.textSecondary} />
      <Txt variant="small" style={{ marginLeft: 6, color: colors.textSecondary }} numberOfLines={1}>{label}</Txt>
    </View>
  );
}

export default function StudentJobs() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("jobs");
  const [jobs, setJobs] = useState<any[]>([]);
  const [apps, setApps] = useState<any[]>([]);
  const [user, setUser] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  // Filters
  const [skill, setSkill] = useState("");
  const [location, setLocation] = useState<string | null>("");
  const [category, setCategory] = useState<string | null>("");
  const [expMin, setExpMin] = useState<string | null>("");
  const [expMax, setExpMax] = useState<string | null>("");
  const [sortBy, setSortBy] = useState<string | null>("newest");
  const [filterError, setFilterError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (skill) params.set("skill", skill);
      if (location) params.set("location", location);
      if (category) params.set("category", category);
      if (expMin) params.set("exp_min", expMin);
      if (expMax) params.set("exp_max", expMax);
      if (sortBy) params.set("sort", sortBy);
      const qs = params.toString();
      const [j, a, me] = await Promise.all([
        api<any[]>(`/jobs${qs ? "?" + qs : ""}`),
        api<any[]>("/applications"),
        api<any>("/auth/me"),
      ]);
      setJobs(j);
      setApps(a);
      setUser(me?.user || null);
    } catch {}
    setRefreshing(false);
  }, [skill, location, category, expMin, expMax, sortBy]);

  useEffect(() => { load(); }, [load]);

  const [applyTarget, setApplyTarget] = useState<any | null>(null);
  const [appliedOk, setAppliedOk] = useState(false);

  function askApply(job: any) { setApplyTarget(job); }
  async function confirmApply() {
    if (!applyTarget) return;
    const jobId = applyTarget.id;
    setApplyTarget(null);
    try {
      await api<{ used_free?: boolean }>("/jobs/apply", { method: "POST", body: { job_id: jobId } });
      setAppliedOk(true);
      load();
    } catch (e: any) {
      const msg = e.message || "";
      if (/insufficient credit/i.test(msg)) {
        Alert.alert("Insufficient credits", "Please add credits to continue applying for this job.", [
          { text: "Add Credits", onPress: () => router.push("/student/wallet") },
          { text: "Cancel", style: "cancel" },
        ]);
      } else {
        Alert.alert("Cannot apply", msg);
      }
    }
  }

  function applyFilters() {
    setFilterError(null);
    // Validation: min <= max for experience filters
    const parse = (v: string | null) => {
      if (!v) return null;
      if (v === "15+") return 15;
      const n = parseInt(v, 10);
      return Number.isFinite(n) ? n : null;
    };
    const mn = parse(expMin);
    const mx = parse(expMax);
    if (mn !== null && mx !== null && mx < mn) {
      setFilterError("Maximum Experience must be ≥ Minimum Experience.");
      return;
    }
    load();
    setShowFilters(false);
  }
  function clearFilters() {
    setSkill(""); setLocation(""); setCategory(""); setExpMin(""); setExpMax(""); setSortBy("newest"); setFilterError(null);
  }

  const avatarUri = user?.profile?.profile_photo_base64 || null;

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Txt variant="h1">Jobs</Txt>
        </View>
        <TouchableOpacity testID="filter-btn" onPress={() => setShowFilters((p) => !p)} style={styles.filterBtn}>
          <Ionicons name="options" size={20} color={colors.textPrimary} />
        </TouchableOpacity>
        <Avatar testID="header-avatar" uri={avatarUri} name={user?.name} size={40} ring onPress={() => router.push("/student/profile")} />
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
          <Picker
            testID="f-location"
            label="Location"
            options={[{ value: "", label: "All locations" }, ...LOCATION_OPTIONS.filter(o => o.value !== "__OTHER__"), { value: "__OTHER__", label: "Others" }]}
            value={location}
            onChange={(v) => setLocation(v as string)}
            placeholder="All"
          />
          <Picker
            testID="f-sort"
            label="Sort By"
            options={JOB_SORT_OPTIONS}
            value={sortBy}
            onChange={(v) => setSortBy(v as string)}
            placeholder="Newest First"
          />
          <View style={{ flexDirection: "row", gap: 8 }}>
            <View style={{ flex: 1 }}>
              <Picker
                testID="f-expmin"
                label="Min Experience"
                options={[{ value: "", label: "Any" }, ...EXP_FILTER_OPTIONS]}
                value={expMin}
                onChange={(v) => setExpMin(v as string)}
                placeholder="Any"
              />
            </View>
            <View style={{ flex: 1 }}>
              <Picker
                testID="f-expmax"
                label="Max Experience"
                options={[{ value: "", label: "Any" }, ...EXP_FILTER_OPTIONS]}
                value={expMax}
                onChange={(v) => setExpMax(v as string)}
                placeholder="Any"
              />
            </View>
          </View>
          <Picker
            testID="f-cat"
            label="Category"
            options={JOB_CATEGORY_FILTER_OPTIONS}
            value={category}
            onChange={(v) => setCategory(v as string)}
            placeholder="All"
          />
          {filterError ? <Txt style={{ color: colors.error, marginTop: -4, marginBottom: 8 }}>{filterError}</Txt> : null}
          <View style={{ flexDirection: "row", alignItems: "center", marginTop: 4 }}>
            <Button testID="f-apply" title="Apply Filter" onPress={applyFilters} style={{ paddingHorizontal: 20 }} />
            <TouchableOpacity testID="f-clear" onPress={clearFilters} style={{ marginLeft: 16 }}>
              <Txt style={{ color: colors.primary, fontWeight: "700" }}>Clear filters</Txt>
            </TouchableOpacity>
          </View>
        </Card>
      ) : null}

      {tab === "jobs" ? (
        <View style={{ gap: 12, marginTop: 16 }}>
          {jobs.length === 0 ? <Txt variant="muted">No jobs match — try adjusting filters.</Txt> : null}
          {jobs.map((j) => (
            <TouchableOpacity
              key={j.id}
              testID={`job-card-${j.id}`}
              activeOpacity={0.9}
              onPress={() => router.push(`/student/jobs/${j.id}`)}
            >
              <Card>
                <View style={{ flexDirection: "row", alignItems: "flex-start" }}>
                  <View style={{ flex: 1, paddingRight: 8 }}>
                    <Txt variant="h3" numberOfLines={1}>{j.title}</Txt>
                    <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }} numberOfLines={1}>
                      {j.company || j.employer_name}
                    </Txt>
                  </View>
                  <View style={styles.statsBox}>
                    <View style={styles.statRow}>
                      <Ionicons name="people" size={12} color={colors.primary} />
                      <Txt variant="small" style={styles.statTxt}>Openings: {openingsLabelOf(j)}</Txt>
                    </View>
                    <View style={styles.statRow}>
                      <Ionicons name="document-text" size={12} color="#7C3AED" />
                      <Txt variant="small" style={styles.statTxt}>Applied: {j.applied_count ?? 0}</Txt>
                    </View>
                    <View style={styles.statRow}>
                      <Ionicons name="checkmark-circle" size={12} color={colors.success} />
                      <Txt variant="small" style={styles.statTxt}>Shortlisted: {j.shortlisted_count ?? 0}</Txt>
                    </View>
                  </View>
                </View>

                {/* Meta rows with icons */}
                <View style={styles.metaGrid}>
                  <View style={{ flex: 1 }}><MetaRow icon="location" label={j.location || "—"} /></View>
                  <View style={{ flex: 1 }}><MetaRow icon="person" label={categoryLabelOf(j)} /></View>
                </View>
                <View style={styles.metaGrid}>
                  <View style={{ flex: 1 }}><MetaRow icon="cash" label={`₹ ${salaryLabelOf(j)}`} /></View>
                  <View style={{ flex: 1 }}><MetaRow icon="briefcase" label={experienceLabelOf(j)} /></View>
                </View>
                <MetaRow icon="business" label={j.industry_type || "—"} />

                {j.description ? (
                  <Txt variant="small" style={{ marginTop: 8, color: colors.textSecondary }} numberOfLines={2}>{j.description}</Txt>
                ) : null}
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
                  <Button testID={`apply-${j.id}`} title="Apply" onPress={() => askApply(j)} style={{ marginTop: 12 }} />
                )}
              </Card>
            </TouchableOpacity>
          ))}
        </View>
      ) : null}

      {tab === "applications" ? (
        <View style={{ gap: 12, marginTop: 16 }}>
          {apps.length === 0 ? <Txt variant="muted">No applications yet.</Txt> : null}
          {apps.map((a) => (
            <TouchableOpacity key={a.id} testID={`app-card-${a.id}`} activeOpacity={0.85} onPress={() => router.push(`/student/applications/${a.id}`)}>
              <Card>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <View style={{ flex: 1 }}>
                    <Txt variant="h3">{a.job_title}</Txt>
                    <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                      {a.referrer_pro_name ? `Referred by ${a.referrer_pro_name}` : "Direct"} · Applied {new Date(a.created_at).toLocaleDateString()}
                    </Txt>
                  </View>
                  <View style={[styles.statusPill, { backgroundColor: statusColor(a.status) }]}>
                    <Txt variant="small" style={{ color: "#fff", fontWeight: "700", textTransform: "capitalize" }}>
                      {(a.status || "").replace(/_/g, " ")}
                    </Txt>
                  </View>
                </View>
              </Card>
            </TouchableOpacity>
          ))}
        </View>
      ) : null}

      <ConfirmDialog
        visible={!!applyTarget}
        title={applyTarget?.applied
          ? "Already applied"
          : (((user?.free_uses_left ?? 0) > 0)
              ? "Free pass available! Apply to this job using your free pass?"
              : "This application will use 49 credits. Do you want to continue?")}
        confirmLabel="Apply"
        cancelLabel="Cancel"
        onCancel={() => setApplyTarget(null)}
        onConfirm={confirmApply}
      />

      <ConfirmDialog
        visible={appliedOk}
        title="Application submitted successfully."
        confirmLabel="OK"
        cancelLabel=""
        onCancel={() => setAppliedOk(false)}
        onConfirm={() => setAppliedOk(false)}
      />
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
  header: { flexDirection: "row", alignItems: "center", gap: 10 },
  filterBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  tabs: { flexDirection: "row", marginTop: 16, backgroundColor: colors.surfaceAlt, borderRadius: 999, padding: 4 },
  tab: { flex: 1, paddingVertical: 10, alignItems: "center", borderRadius: 999 },
  tabActive: { backgroundColor: colors.primary },
  chip: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  appliedPill: { flexDirection: "row", alignItems: "center", backgroundColor: "#E6F9F0", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 999, alignSelf: "flex-start" },
  statusPill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 },
  statsBox: { alignItems: "flex-end", gap: 2 },
  statRow: { flexDirection: "row", alignItems: "center" },
  statTxt: { marginLeft: 4, fontSize: 11, fontWeight: "700", color: colors.textPrimary },
  metaGrid: { flexDirection: "row", marginTop: 6, gap: 8 },
  metaRow: { flexDirection: "row", alignItems: "center", marginTop: 4 },
});
