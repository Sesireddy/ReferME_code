import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, Alert, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { ScreenTitle } from "@/src/components/ScreenTitle";
import { Button } from "@/src/components/Button";
import { Picker } from "@/src/components/Picker";
import { SkillAutocomplete } from "@/src/components/SkillAutocomplete";
import { ConfirmDialog } from "@/src/components/ConfirmDialog";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import {
  LOCATION_OPTIONS,
  JOB_SORT_OPTIONS,
  JOB_CATEGORY_FILTER_OPTIONS,
  SALARY_RANGE_OPTIONS,
  SKILL_OPTIONS,
  INDUSTRY_OPTIONS,
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
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  // Iteration 59 — track whether the first fetch has completed. Prevents the
  // "No jobs found matching the selected filters." empty-state from flashing on
  // the initial load (which used to show for ~5s before the API returned).
  const [initialLoading, setInitialLoading] = useState(true);
  const [showFilters, setShowFilters] = useState(false);

  // Filters
  const [skill, setSkill] = useState<string | null>("");
  const [location, setLocation] = useState<string | null>("");
  const [category, setCategory] = useState<string | null>("");
  const [industry, setIndustry] = useState<string | null>("");
  const [sortBy, setSortBy] = useState<string | null>("newest");

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (skill) params.set("skill", skill);
      if (location) params.set("location", location);
      if (category) params.set("category", category);
      if (industry) params.set("industry", industry);
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
      setMissingFields(Array.isArray(me?.missing_fields) ? me.missing_fields : []);
    } catch {}
    setRefreshing(false);
    setInitialLoading(false);
  }, [skill, location, category, industry, sortBy]);

  useEffect(() => { load(); }, [load]);

  const [applyTarget, setApplyTarget] = useState<any | null>(null);
  const [appliedOk, setAppliedOk] = useState(false);

  // Iteration 58 — show the "Complete Your Profile" popup any time a Job Seeker
  // taps Apply while their profile is missing mandatory fields. Uses the spec copy
  // exactly (title / body / Complete Profile / Cancel).
  function showCompleteProfilePopup(missing?: string[]) {
    const list = (missing && missing.length ? missing : missingFields).slice(0, 5);
    const suffix = list.length
      ? `\n\nStill needed:\n• ${list.join("\n• ")}`
      : "";
    Alert.alert(
      "Complete Your Profile",
      `Please complete your profile before applying for jobs. A complete profile helps Working Professionals and Employers evaluate your application more effectively.${suffix}`,
      [
        { text: "Complete Profile", onPress: () => router.push("/student/profile") },
        { text: "Cancel", style: "cancel" },
      ],
    );
  }

  function askApply(job: any) {
    if (missingFields.length > 0) {
      showCompleteProfilePopup();
      return;
    }
    setApplyTarget(job);
  }
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
      // Backend may return a structured PROFILE_INCOMPLETE error with the missing list.
      const detail = (e as any).detail;
      if (detail && typeof detail === "object" && detail.code === "PROFILE_INCOMPLETE") {
        showCompleteProfilePopup(detail.missing_fields || []);
      } else if (/PROFILE_INCOMPLETE|complete your profile/i.test(msg)) {
        showCompleteProfilePopup();
      } else if (/insufficient credit/i.test(msg)) {
        Alert.alert(
          "Insufficient Credits",
          "You don't have enough credits to apply for this job. Please add credits to your wallet to continue.",
          [
            { text: "Cancel", style: "cancel" },
            { text: "Add Credits", onPress: () => router.push("/student/wallet") },
          ],
        );
      } else if (/already applied/i.test(msg)) {
        Alert.alert("Already Applied", "You have already applied for this job.", [{ text: "OK" }]);
      } else if (/applications closed|no longer accepting|job not available|not open|closed/i.test(msg)) {
        Alert.alert("Job Unavailable", "This job is no longer accepting applications.", [
          { text: "OK", onPress: () => load() },
        ]);
      } else {
        Alert.alert("Cannot apply", msg);
      }
    }
  }

  function applyFilters() {
    load();
    setShowFilters(false);
  }
  function clearFilters() {
    setSkill(""); setLocation(""); setCategory(""); setIndustry(""); setSortBy("newest");
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <ScreenTitle title="Jobs" icon="briefcase" color={colors.primary} />
        </View>
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
          <Picker
            testID="f-location"
            label="Location"
            options={[{ value: "", label: "All locations" }, ...LOCATION_OPTIONS.filter(o => o.value !== "__OTHER__"), { value: "__OTHER__", label: "Others" }]}
            value={location}
            onChange={(v) => setLocation(v as string)}
            placeholder="All"
          />
          <Picker
            testID="f-cat"
            label="Category"
            options={JOB_CATEGORY_FILTER_OPTIONS}
            value={category}
            onChange={(v) => setCategory(v as string)}
            placeholder="All"
          />
          <SkillAutocomplete
            testID="f-skill"
            label="Skill Set"
            value={skill || ""}
            onChange={(v) => setSkill(v)}
            placeholder="Search or Select Skill"
          />
          <Picker
            testID="f-industry"
            label="Industry Type"
            options={[{ value: "", label: "All industries" }, ...INDUSTRY_OPTIONS.filter(o => o.value !== "__OTHER__"), { value: "Other", label: "Other" }]}
            value={industry}
            onChange={(v) => setIndustry(v as string)}
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
          {initialLoading ? (
            <Card>
              <View style={{ alignItems: "center", paddingVertical: 24 }}>
                <ActivityIndicator size="large" color={colors.primary} />
                <Txt variant="h3" style={{ marginTop: 12, textAlign: "center" }}>Loading jobs…</Txt>
                <Txt variant="small" style={{ marginTop: 4, color: colors.textSecondary, textAlign: "center" }}>
                  Fetching the latest openings for you.
                </Txt>
              </View>
            </Card>
          ) : jobs.length === 0 ? (
            <Card>
              <View style={{ alignItems: "center", paddingVertical: 16 }}>
                <Ionicons name="search-circle-outline" size={48} color={colors.textSecondary} />
                <Txt variant="h3" style={{ marginTop: 8, textAlign: "center" }}>No jobs found matching the selected filters.</Txt>
                <TouchableOpacity testID="empty-clear" onPress={clearFilters} style={{ marginTop: 8 }}>
                  <Txt style={{ color: colors.primary, fontWeight: "700" }}>Clear filters</Txt>
                </TouchableOpacity>
              </View>
            </Card>
          ) : null}
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
                  <View style={{ flex: 1 }}>
                    <MetaRow
                      icon="location"
                      label={(Array.isArray(j.locations) && j.locations.length > 0 ? j.locations : (j.location ? [j.location] : ["—"])).join(" • ")}
                    />
                  </View>
                  <View style={{ flex: 1 }}><MetaRow icon="person" label={categoryLabelOf(j)} /></View>
                </View>
                <View style={styles.metaGrid}>
                  <View style={{ flex: 1 }}><MetaRow icon="cash" label={`₹ ${salaryLabelOf(j)}`} /></View>
                  <View style={{ flex: 1 }}><MetaRow icon="briefcase" label={experienceLabelOf(j)} /></View>
                </View>
                <MetaRow icon="business" label={j.industry_type || "—"} />
                {j.last_date_to_apply ? (
                  <MetaRow
                    icon="time"
                    label={`Apply by ${new Date(j.last_date_to_apply).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" })}`}
                  />
                ) : null}

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

                {j.is_closed ? (
                  <View style={[styles.closedPill, { marginTop: 12 }]}>
                    <Ionicons name="lock-closed" size={16} color={colors.error} />
                    <Txt style={{ color: colors.error, fontWeight: "800", marginLeft: 6 }}>
                      🔴 Applications Closed
                    </Txt>
                  </View>
                ) : j.applied ? (
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
          {initialLoading ? (
            <Card>
              <View style={{ alignItems: "center", paddingVertical: 24 }}>
                <ActivityIndicator size="large" color={colors.primary} />
                <Txt variant="h3" style={{ marginTop: 12, textAlign: "center" }}>Loading applications…</Txt>
              </View>
            </Card>
          ) : apps.length === 0 ? (
            <Txt variant="muted">No applications yet.</Txt>
          ) : null}
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
        title="Apply for Job"
        message={applyTarget?.applied
          ? "You have already applied for this job."
          : (((user?.free_uses_left ?? 0) > 0)
              ? "You have a free pass available! Apply to this job using your free pass?"
              : `Applying for this job will deduct ${user?.action_cost ?? 99} credits from your wallet. Do you want to continue?`)}
        confirmLabel="Apply"
        cancelLabel="Cancel"
        onCancel={() => setApplyTarget(null)}
        onConfirm={confirmApply}
      />

      <ConfirmDialog
        visible={appliedOk}
        title="Application Submitted"
        message={`Your application has been submitted successfully. ${user?.action_cost ?? 99} credits have been deducted from your wallet.`}
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
  closedPill: { flexDirection: "row", alignItems: "center", backgroundColor: "#FEE2E2", borderWidth: 1, borderColor: "#DC2626", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 999, alignSelf: "flex-start" },
  statusPill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 },
  statsBox: { alignItems: "flex-end", gap: 2 },
  statRow: { flexDirection: "row", alignItems: "center" },
  statTxt: { marginLeft: 4, fontSize: 11, fontWeight: "700", color: colors.textPrimary },
  metaGrid: { flexDirection: "row", marginTop: 6, gap: 8 },
  metaRow: { flexDirection: "row", alignItems: "center", marginTop: 4 },
});
