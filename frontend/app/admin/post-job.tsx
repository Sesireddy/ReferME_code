// Admin — Post a Job screen. Publishes walk-in / direct hiring jobs that appear
// under the Job Seeker "Walk-in & Direct Jobs" section (no credit deduction,
// no approval flow, Details-only view — no Apply button).
import React, { useEffect, useState } from "react";
import { View, StyleSheet, TouchableOpacity, ScrollView, Alert, Image } from "react-native";
import { Stack, useRouter, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { LocationMultiSelect } from "@/src/components/LocationMultiSelect";
import { DatePickerField } from "@/src/components/DateTimePicker";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { successAlert } from "@/src/lib/successAlert";
import { webSafeAlert } from "@/src/lib/webSafeAlert";

const EMPLOYMENT_TYPES = ["Full-time", "Part-time", "Contract", "Internship", "Walk-in Drive"];

type FormState = {
  company: string;
  title: string;
  description: string;
  locations: string[];
  last_date_to_apply: string; // yyyy-mm-dd (mandatory when publishing)
  experience_min: string;
  experience_max: string;
  skills: string; // comma separated
  open_positions: string;
  employment_type: string;
  salary_range: string;
  walk_in_date: string; // yyyy-mm-dd
  walk_in_time: string;
  venue: string;
  contact_person: string;
  contact_number: string;
  contact_email: string;
  application_deadline: string;
  company_logo_b64: string;
  company_logo_mime: string;
  company_logo_uri: string;
};

const EMPTY: FormState = {
  company: "", title: "", description: "", locations: [],
  last_date_to_apply: "",
  experience_min: "0", experience_max: "", skills: "",
  open_positions: "1", employment_type: "Full-time", salary_range: "",
  walk_in_date: "", walk_in_time: "", venue: "",
  contact_person: "", contact_number: "", contact_email: "",
  application_deadline: "",
  company_logo_b64: "", company_logo_mime: "", company_logo_uri: "",
};

export default function AdminPostJob() {
  const router = useRouter();
  const { editId } = useLocalSearchParams<{ editId?: string }>();
  const isEdit = !!editId;
  const [f, setF] = useState<FormState>(EMPTY);
  const [busy, setBusy] = useState<"" | "publish" | "draft">("");
  const [loading, setLoading] = useState<boolean>(isEdit);

  // In edit mode, hydrate the form from the existing job.
  useEffect(() => {
    if (!editId) return;
    (async () => {
      setLoading(true);
      try {
        const rows: any[] = await api("/admin/jobs/mine");
        const j = (rows || []).find((r) => r.id === editId);
        if (!j) { webSafeAlert("Job not found", "This job could not be loaded for editing."); router.back(); return; }
        setF({
          company: j.company || "",
          title: j.title || "",
          description: j.description || "",
          locations: Array.isArray(j.locations) && j.locations.length > 0
            ? j.locations
            : (j.location ? [j.location] : []),
          last_date_to_apply: j.last_date_to_apply || "",
          experience_min: String(j.experience_min ?? 0),
          experience_max: j.experience_max != null ? String(j.experience_max) : "",
          skills: (j.skills_required || []).join(", "),
          open_positions: String(j.open_positions ?? 1),
          employment_type: j.employment_type || "Full-time",
          salary_range: j.salary_range || "",
          walk_in_date: j.walk_in_date || "",
          walk_in_time: j.walk_in_time || "",
          venue: j.venue || "",
          contact_person: j.contact_person || "",
          contact_number: j.contact_number || "",
          contact_email: j.contact_email || "",
          application_deadline: j.application_deadline || "",
          company_logo_b64: j.company_logo_b64 || "",
          company_logo_mime: j.company_logo_mime || "",
          company_logo_uri: j.company_logo_b64 || "",
        });
      } catch (e: any) { webSafeAlert("Load failed", e?.message || "Could not load job."); }
      finally { setLoading(false); }
    })();
  }, [editId]);

  const setField = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((p) => ({ ...p, [k]: v }));

  async function pickLogo() {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) return webSafeAlert("Permission required", "Please allow photo library access to upload the logo.");
      const res = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: true, quality: 0.6, base64: true,
      });
      if (res.canceled || !res.assets?.length) return;
      const a = res.assets[0];
      const mime = a.mimeType || "image/jpeg";
      setF((p) => ({ ...p, company_logo_b64: `data:${mime};base64,${a.base64}`, company_logo_mime: mime, company_logo_uri: a.uri }));
    } catch (e: any) { webSafeAlert("Could not pick image", String(e?.message || e)); }
  }

  function validate(isDraft: boolean): string | null {
    if (!f.company.trim() || f.company.trim().length < 2) return "Company Name is required.";
    if (!f.title.trim() || f.title.trim().length < 2) return "Job Title is required.";
    if (!f.description.trim() || f.description.trim().length < 10) return "Job Description must be at least 10 characters.";
    if (f.locations.length === 0) return "Please select at least one Location.";
    const today = new Date().toISOString().slice(0, 10);
    if (!isDraft) {
      if (!f.last_date_to_apply) return "Please select the Last Date to Apply.";
      if (f.last_date_to_apply < today) return "Last Date to Apply cannot be earlier than today's date.";
    } else if (f.last_date_to_apply && f.last_date_to_apply < today) {
      return "Last Date to Apply cannot be earlier than today's date.";
    }
    const skills = f.skills.split(",").map((s) => s.trim()).filter(Boolean);
    if (skills.length === 0) return "At least one Skill is required.";
    const positions = parseInt(f.open_positions || "0", 10);
    if (!positions || positions < 1) return "Open Positions must be a positive integer.";
    if (f.contact_number.trim() && !/^[6-9]\d{9}$/.test(f.contact_number.trim())) return "Contact Number must be a valid 10-digit Indian mobile.";
    if (f.contact_email.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.contact_email.trim())) return "Contact Email is not valid.";
    if (!isDraft) {
      for (const [k, v] of [["walk_in_date", f.walk_in_date], ["application_deadline", f.application_deadline]] as const) {
        if (v && v < today) return `${k.replace("_", " ")} must be today or a future date.`;
      }
    }
    if (f.experience_max && f.experience_min && parseInt(f.experience_max) < parseInt(f.experience_min)) return "Max experience must be ≥ Min.";
    return null;
  }

  async function submit(status: "open" | "draft") {
    const isDraft = status === "draft";
    const err = validate(isDraft);
    if (err) return webSafeAlert("Please fix the form", err);
    setBusy(isDraft ? "draft" : "publish");
    try {
      const body = {
        company: f.company.trim(),
        title: f.title.trim(),
        description: f.description.trim(),
        locations: f.locations,
        last_date_to_apply: f.last_date_to_apply || null,
        skills_required: f.skills.split(",").map((s) => s.trim()).filter(Boolean),
        experience_min: parseInt(f.experience_min || "0", 10),
        experience_max: f.experience_max ? parseInt(f.experience_max, 10) : null,
        open_positions: parseInt(f.open_positions || "1", 10),
        employment_type: f.employment_type,
        salary_range: f.salary_range.trim(),
        walk_in_date: f.walk_in_date.trim(),
        walk_in_time: f.walk_in_time.trim(),
        venue: f.venue.trim(),
        contact_person: f.contact_person.trim(),
        contact_number: f.contact_number.trim(),
        contact_email: f.contact_email.trim(),
        application_deadline: f.application_deadline.trim(),
        company_logo_b64: f.company_logo_b64,
        company_logo_mime: f.company_logo_mime,
        status,
      };
      if (isEdit) {
        await api(`/admin/jobs/${editId}`, { method: "PATCH", body });
      } else {
        await api("/admin/jobs", { method: "POST", body });
      }
      successAlert.show({
        title: isEdit
          ? (isDraft ? "Draft Updated" : "Job Updated 🎉")
          : (isDraft ? "Draft Saved" : "Job Published 🎉"),
        message: isDraft
          ? "You can resume editing from My Posted Jobs."
          : "This job is now visible under Walk-in & Direct Jobs.",
      });
      setF(EMPTY);
      router.replace("/admin/my-posted-jobs");
    } catch (e: any) {
      Alert.alert("Error", e?.message || "Could not save job.");
    } finally {
      setBusy("");
    }
  }

  return (
    <Screen keyboardOffset={0}>
      <Stack.Screen options={{ title: isEdit ? "Edit Job" : "Post a Job" }} />
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
        <Txt variant="h1">{isEdit ? "Edit Job" : "Post a Job"}</Txt>
        <Txt variant="muted" style={{ marginTop: 4, marginBottom: 16 }}>
          {loading ? "Loading job…" : "Walk-in Drives · Direct Hiring · Campus & Mass Recruitment. Published jobs go live immediately for free access."}
        </Txt>

        <Card>
          <Txt variant="h3" style={{ marginBottom: 8 }}>Basic Details</Txt>
          <Input label="Company Name *" value={f.company} onChangeText={(v) => setField("company", v)} placeholder="e.g. TCS" testID="admin-job-company" />
          <Input label="Job Title *" value={f.title} onChangeText={(v) => setField("title", v)} placeholder="e.g. Software Engineer" testID="admin-job-title" />
          <Input label="Job Description *" value={f.description} onChangeText={(v) => setField("description", v)} placeholder="Role, responsibilities, must-haves…" multiline numberOfLines={4} testID="admin-job-description" />
          <LocationMultiSelect
            testID="admin-job-location"
            label="Location * (select one or more)"
            value={f.locations}
            onChange={(v) => setField("locations", v)}
            placeholder="Search Location…"
          />
          <DatePickerField
            testID="admin-job-last-date"
            label="Last Date to Apply *"
            value={f.last_date_to_apply}
            onChange={(v) => setField("last_date_to_apply", v)}
            placeholder="Select Last Date to Apply"
            maxDate={new Date(Date.now() + 365 * 86400000)}
          />
        </Card>

        <Card style={{ marginTop: 12 }}>
          <Txt variant="h3" style={{ marginBottom: 8 }}>Role Requirements</Txt>
          <Input label="Skills Required * (comma separated)" value={f.skills} onChangeText={(v) => setField("skills", v)} placeholder="React, Node.js, SQL" testID="admin-job-skills" />
          <View style={{ flexDirection: "row", gap: 10 }}>
            <View style={{ flex: 1 }}><Input label="Experience Min (years)" value={f.experience_min} onChangeText={(v) => setField("experience_min", v.replace(/\D/g, ""))} keyboardType="number-pad" testID="admin-job-exp-min" /></View>
            <View style={{ flex: 1 }}><Input label="Experience Max (years)" value={f.experience_max} onChangeText={(v) => setField("experience_max", v.replace(/\D/g, ""))} keyboardType="number-pad" testID="admin-job-exp-max" /></View>
          </View>
          <Input label="Number of Open Positions *" value={f.open_positions} onChangeText={(v) => setField("open_positions", v.replace(/\D/g, ""))} keyboardType="number-pad" testID="admin-job-openings" />
          <Txt variant="label" style={{ marginBottom: 6, marginTop: 6 }}>Employment Type</Txt>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
            {EMPLOYMENT_TYPES.map((t) => (
              <TouchableOpacity key={t} onPress={() => setField("employment_type", t)} style={[styles.chip, f.employment_type === t && styles.chipActive]}>
                <Txt style={{ color: f.employment_type === t ? "#fff" : colors.textPrimary, fontWeight: "600", fontSize: 13 }}>{t}</Txt>
              </TouchableOpacity>
            ))}
          </View>
          <Input label="Salary (Optional)" value={f.salary_range} onChangeText={(v) => setField("salary_range", v)} placeholder="e.g. ₹6-10 LPA" testID="admin-job-salary" />
        </Card>

        <Card style={{ marginTop: 12 }}>
          <Txt variant="h3" style={{ marginBottom: 8 }}>Walk-in / Direct Hire (Optional)</Txt>
          <Input label="Walk-in Date (YYYY-MM-DD)" value={f.walk_in_date} onChangeText={(v) => setField("walk_in_date", v)} placeholder="2026-07-15" testID="admin-job-walkin-date" />
          <Input label="Walk-in Time" value={f.walk_in_time} onChangeText={(v) => setField("walk_in_time", v)} placeholder="10:00 AM – 4:00 PM" testID="admin-job-walkin-time" />
          <Input label="Venue / Interview Address" value={f.venue} onChangeText={(v) => setField("venue", v)} placeholder="TCS Office, Bengaluru" multiline testID="admin-job-venue" />
        </Card>

        <Card style={{ marginTop: 12 }}>
          <Txt variant="h3" style={{ marginBottom: 8 }}>Contact</Txt>
          <Input label="Contact Person" value={f.contact_person} onChangeText={(v) => setField("contact_person", v)} placeholder="Priya HR" testID="admin-job-contact-person" />
          <Input label="Contact Number" value={f.contact_number} onChangeText={(v) => setField("contact_number", v.replace(/\D/g, "").slice(0, 10))} keyboardType="phone-pad" placeholder="10-digit mobile" testID="admin-job-contact-number" />
          <Input label="Contact Email" value={f.contact_email} onChangeText={(v) => setField("contact_email", v)} keyboardType="email-address" autoCapitalize="none" placeholder="hr@company.com" testID="admin-job-contact-email" />
          <Input label="Application Last Date (YYYY-MM-DD)" value={f.application_deadline} onChangeText={(v) => setField("application_deadline", v)} placeholder="2026-07-31" testID="admin-job-deadline" />
        </Card>

        <Card style={{ marginTop: 12 }}>
          <Txt variant="h3" style={{ marginBottom: 8 }}>Company Logo (Optional)</Txt>
          {f.company_logo_uri ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
              <Image source={{ uri: f.company_logo_uri }} style={{ width: 72, height: 72, borderRadius: 12 }} />
              <TouchableOpacity onPress={() => setF((p) => ({ ...p, company_logo_b64: "", company_logo_mime: "", company_logo_uri: "" }))} style={styles.smallBtn}>
                <Ionicons name="close" size={16} color={colors.error} />
                <Txt style={{ marginLeft: 4, color: colors.error, fontWeight: "700" }}>Remove</Txt>
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity testID="admin-job-pick-logo" onPress={pickLogo} style={styles.uploadBtn}>
              <Ionicons name="image" size={18} color={colors.primary} />
              <Txt style={{ color: colors.primary, fontWeight: "700", marginLeft: 6 }}>Upload logo</Txt>
            </TouchableOpacity>
          )}
        </Card>

        <View style={{ marginTop: 20, gap: 8 }}>
          <Button testID="admin-job-publish" title={isEdit ? "Save & Publish" : "Publish Job"} loading={busy === "publish"} onPress={() => submit("open")} />
          <Button testID="admin-job-save-draft" title="Save Draft" variant="secondary" loading={busy === "draft"} onPress={() => submit("draft")} />
          <Button testID="admin-job-cancel" title="Cancel" variant="ghost" onPress={() => router.back()} />
        </View>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  chip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.md, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  uploadBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", paddingVertical: 12, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primary + "12" },
  smallBtn: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.md, backgroundColor: colors.error + "14" },
});
