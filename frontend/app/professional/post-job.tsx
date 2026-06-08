import React, { useState } from "react";
import { View, Alert, StyleSheet } from "react-native";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { Picker } from "@/src/components/Picker";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

const CATEGORY_OPTIONS = [
  { value: "fresher", label: "Fresher" },
  { value: "experienced", label: "Experienced" },
];

const OPEN_POSITIONS_OPTIONS = [
  { value: "1 to 5", label: "1 to 5" },
  { value: "1 to 10", label: "1 to 10" },
  { value: "1 to 50", label: "1 to 50" },
  { value: "1 to 100", label: "1 to 100" },
  { value: "100+", label: "100+" },
];

type Errors = Partial<Record<"title" | "company" | "desc" | "location" | "category" | "skills" | "openings" | "expReq", string>>;

export default function ProPostJob() {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [desc, setDesc] = useState("");
  const [location, setLocation] = useState("");
  const [category, setCategory] = useState<string | null>("fresher");
  const [expReq, setExpReq] = useState("0");
  const [skills, setSkills] = useState("");
  const [openings, setOpenings] = useState<string | null>("1 to 5");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [success, setSuccess] = useState(false);

  function validate(): Errors {
    const e: Errors = {};
    if (!title.trim()) e.title = "Job Title is required.";
    if (!company.trim()) e.company = "Company Name is required.";
    if (!desc.trim()) e.desc = "Job Description is required.";
    if (!location.trim()) e.location = "Location is required.";
    if (!category) e.category = "Category is required.";
    if (skills.split(",").map((s) => s.trim()).filter(Boolean).length === 0) e.skills = "Skill Set is required.";
    if (!openings) e.openings = "Number of Open Positions is required.";
    if (category === "experienced" && (!expReq || parseInt(expReq, 10) <= 0)) e.expReq = "Years of experience must be > 0 for Experienced roles.";
    return e;
  }

  async function post() {
    setSuccess(false);
    const v = validate();
    setErrors(v);
    if (Object.keys(v).length) return;
    setBusy(true);
    try {
      await api("/jobs", {
        method: "POST",
        body: {
          title: title.trim(),
          company: company.trim(),
          description: desc.trim(),
          location: location.trim(),
          category,
          experience_required: category === "experienced" ? parseInt(expReq, 10) : 0,
          skills_required: skills.split(",").map((s) => s.trim()).filter(Boolean),
          open_positions_label: openings,
        },
      });
      setSuccess(true);
      setTitle(""); setCompany(""); setDesc(""); setLocation(""); setExpReq("0"); setSkills(""); setOpenings("1 to 5"); setCategory("fresher");
      setErrors({});
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally { setBusy(false); }
  }

  return (
    <Screen>
      <Txt variant="h1">Post a job opening</Txt>
      <Txt variant="muted">Open jobs at your company — refer candidates and earn ₹1500/hire.</Txt>
      {success ? (
        <Card style={{ marginTop: 12, backgroundColor: "#E8F5E9", borderColor: "#2E7D32", borderWidth: 1 }}>
          <Txt style={{ color: "#2E7D32", fontWeight: "700" }}>Job Posted Successfully ✅</Txt>
        </Card>
      ) : null}
      <Card style={{ marginTop: 16 }}>
        <Input testID="pj-title" label="Job Title *" value={title} onChangeText={(v) => { setTitle(v); setErrors((e) => ({ ...e, title: undefined })); }} placeholder="Frontend Engineer" />
        {errors.title ? <Txt style={styles.err}>{errors.title}</Txt> : null}
        <Input testID="pj-company" label="Company Name *" value={company} onChangeText={(v) => { setCompany(v); setErrors((e) => ({ ...e, company: undefined })); }} placeholder="Acme Corp" />
        {errors.company ? <Txt style={styles.err}>{errors.company}</Txt> : null}
        <Input testID="pj-desc" label="Job Description *" value={desc} onChangeText={(v) => { setDesc(v); setErrors((e) => ({ ...e, desc: undefined })); }} multiline placeholder="Role, responsibilities, etc." />
        {errors.desc ? <Txt style={styles.err}>{errors.desc}</Txt> : null}
        <Input testID="pj-loc" label="Location *" value={location} onChangeText={(v) => { setLocation(v); setErrors((e) => ({ ...e, location: undefined })); }} placeholder="Bengaluru / Remote" />
        {errors.location ? <Txt style={styles.err}>{errors.location}</Txt> : null}
        <Picker
          testID="pj-category"
          label="Category *"
          options={CATEGORY_OPTIONS}
          value={category}
          onChange={(v) => { setCategory(v as string); setErrors((e) => ({ ...e, category: undefined })); }}
          placeholder="Fresher / Experienced"
        />
        {errors.category ? <Txt style={styles.err}>{errors.category}</Txt> : null}
        {category === "experienced" ? (
          <>
            <Input testID="pj-exp" label="Years of Experience Required *" value={expReq} onChangeText={(v) => { setExpReq(v); setErrors((e) => ({ ...e, expReq: undefined })); }} keyboardType="number-pad" />
            {errors.expReq ? <Txt style={styles.err}>{errors.expReq}</Txt> : null}
          </>
        ) : null}
        <Input testID="pj-skills" label="Skill Set (comma-separated) *" value={skills} onChangeText={(v) => { setSkills(v); setErrors((e) => ({ ...e, skills: undefined })); }} placeholder="React Native, TypeScript" />
        {errors.skills ? <Txt style={styles.err}>{errors.skills}</Txt> : null}
        <Picker
          testID="pj-openings"
          label="Number of Open Positions *"
          options={OPEN_POSITIONS_OPTIONS}
          value={openings}
          onChange={(v) => { setOpenings(v as string); setErrors((e) => ({ ...e, openings: undefined })); }}
          placeholder="1 to 5"
        />
        {errors.openings ? <Txt style={styles.err}>{errors.openings}</Txt> : null}
        <Button testID="pj-submit" title="Post job" loading={busy} onPress={post} style={{ marginTop: 8 }} />
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  err: { color: colors.error, fontSize: 12, marginTop: -8, marginBottom: 8 },
});
