import React, { useState } from "react";
import { View, Alert, StyleSheet } from "react-native";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { Picker } from "@/src/components/Picker";
import { ConfirmDialog } from "@/src/components/ConfirmDialog";
import { ScreenTitle } from "@/src/components/ScreenTitle";
import {
  LOCATION_OPTIONS,
  SALARY_RANGE_OPTIONS,
  INDUSTRY_OPTIONS,
  EXP_FILTER_OPTIONS,
} from "@/src/lib/constants";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

const CATEGORY_OPTIONS = [
  { value: "fresher", label: "Fresher" },
  { value: "experienced", label: "Experienced" },
  { value: "intern", label: "Intern" },
];

const OPEN_POSITIONS_OPTIONS = [
  { value: "1 to 5", label: "1 to 5" },
  { value: "1 to 10", label: "1 to 10" },
  { value: "1 to 50", label: "1 to 50" },
  { value: "1 to 100", label: "1 to 100" },
  { value: "100+", label: "100+" },
];

type Errors = Partial<Record<
  "title" | "company" | "desc" | "location" | "locationOther" | "salary" | "industry" |
  "industryOther" | "category" | "skills" | "openings" | "expMin" | "expMax",
  string
>>;

export default function ProPostJob() {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [desc, setDesc] = useState("");
  const [location, setLocation] = useState<string | null>(null);
  const [locationOther, setLocationOther] = useState("");
  const [salaryRange, setSalaryRange] = useState<string | null>(null);
  const [industry, setIndustry] = useState<string | null>(null);
  const [industryOther, setIndustryOther] = useState("");
  const [category, setCategory] = useState<string | null>("fresher");
  const [expMin, setExpMin] = useState<string | null>(null);
  const [expMax, setExpMax] = useState<string | null>(null);
  const [skills, setSkills] = useState("");
  const [openings, setOpenings] = useState<string | null>("1 to 5");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [success, setSuccess] = useState(false);

  const isExperienced = category === "experienced";
  const isOtherLoc = location === "__OTHER__";
  const isOtherInd = industry === "__OTHER__";

  function parseExp(v: string | null): number | null {
    if (!v) return null;
    if (v === "15+") return 15;
    const n = parseInt(v, 10);
    return Number.isFinite(n) ? n : null;
  }

  function validate(): Errors {
    const e: Errors = {};
    if (!title.trim()) e.title = "Job Title is required.";
    if (!company.trim()) e.company = "Company Name is required.";
    if (!desc.trim()) e.desc = "Job Description is required.";
    if (!location) e.location = "Location is required.";
    if (isOtherLoc && !locationOther.trim()) e.locationOther = "Please specify the city.";
    if (!salaryRange) e.salary = "Salary Range is required.";
    if (!industry) e.industry = "Industry Type is required.";
    if (isOtherInd && !industryOther.trim()) e.industryOther = "Please specify the industry.";
    if (!category) e.category = "Category is required.";
    if (skills.split(",").map((s) => s.trim()).filter(Boolean).length === 0) e.skills = "Skill Set is required.";
    if (!openings) e.openings = "Number of Open Positions is required.";
    if (isExperienced) {
      const mn = parseExp(expMin);
      const mx = parseExp(expMax);
      if (mn === null) e.expMin = "Select minimum experience.";
      if (mx === null) e.expMax = "Select maximum experience.";
      if (mn !== null && mx !== null && mx < mn) e.expMax = "Maximum must be ≥ Minimum.";
    }
    return e;
  }

  async function post() {
    setSuccess(false);
    const v = validate();
    setErrors(v);
    if (Object.keys(v).length) return;
    setBusy(true);
    try {
      const mn = parseExp(expMin);
      const mx = parseExp(expMax);
      await api("/jobs", {
        method: "POST",
        body: {
          title: title.trim(),
          company: company.trim(),
          description: desc.trim(),
          location,
          location_other: isOtherLoc ? locationOther.trim() : null,
          salary_range_label: salaryRange,
          industry_type: industry,
          industry_other: isOtherInd ? industryOther.trim() : null,
          category,
          experience_required: isExperienced ? (mn ?? 0) : 0,
          experience_min: isExperienced ? mn : 0,
          experience_max: isExperienced ? mx : 0,
          skills_required: skills.split(",").map((s) => s.trim()).filter(Boolean),
          open_positions_label: openings,
        },
      });
      setSuccess(true);
      // Reset
      setTitle(""); setCompany(""); setDesc(""); setLocation(null); setLocationOther("");
      setSalaryRange(null); setIndustry(null); setIndustryOther("");
      setCategory("fresher"); setExpMin(null); setExpMax(null);
      setSkills(""); setOpenings("1 to 5");
      setErrors({});
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally { setBusy(false); }
  }

  return (
    <Screen>
      <ScreenTitle
        title="Post a Job"
        icon="add-circle"
        color="#7C3AED"
        subtitle="Open jobs at your company — refer candidates and earn ₹1500/hire."
      />
      <ConfirmDialog
        visible={success}
        title="Job posted successfully."
        confirmLabel="OK"
        cancelLabel=""
        onCancel={() => setSuccess(false)}
        onConfirm={() => setSuccess(false)}
      />
      <Card style={{ marginTop: 16 }}>
        <Input testID="pj-title" label="Job Title *" value={title} onChangeText={(v) => { setTitle(v); setErrors((e) => ({ ...e, title: undefined })); }} placeholder="Frontend Engineer" />
        {errors.title ? <Txt style={styles.err}>{errors.title}</Txt> : null}

        <Input testID="pj-company" label="Company Name *" value={company} onChangeText={(v) => { setCompany(v); setErrors((e) => ({ ...e, company: undefined })); }} placeholder="Acme Corp" />
        {errors.company ? <Txt style={styles.err}>{errors.company}</Txt> : null}

        <Input testID="pj-desc" label="Job Description *" value={desc} onChangeText={(v) => { setDesc(v); setErrors((e) => ({ ...e, desc: undefined })); }} multiline placeholder="Role, responsibilities, etc." />
        {errors.desc ? <Txt style={styles.err}>{errors.desc}</Txt> : null}

        <Picker
          testID="pj-loc"
          label="Location *"
          options={LOCATION_OPTIONS}
          value={location}
          onChange={(v) => { setLocation(v as string); setErrors((e) => ({ ...e, location: undefined })); }}
          placeholder="Select city"
        />
        {errors.location ? <Txt style={styles.err}>{errors.location}</Txt> : null}
        {isOtherLoc ? (
          <>
            <Input testID="pj-loc-other" label="Specify Location *" value={locationOther} onChangeText={(v) => { setLocationOther(v); setErrors((e) => ({ ...e, locationOther: undefined })); }} placeholder="City name" />
            {errors.locationOther ? <Txt style={styles.err}>{errors.locationOther}</Txt> : null}
          </>
        ) : null}

        <Picker
          testID="pj-salary"
          label="Salary Range *"
          options={SALARY_RANGE_OPTIONS}
          value={salaryRange}
          onChange={(v) => { setSalaryRange(v as string); setErrors((e) => ({ ...e, salary: undefined })); }}
          placeholder="Select salary range"
        />
        {errors.salary ? <Txt style={styles.err}>{errors.salary}</Txt> : null}

        <Picker
          testID="pj-industry"
          label="Industry Type *"
          options={INDUSTRY_OPTIONS}
          value={industry}
          onChange={(v) => { setIndustry(v as string); setErrors((e) => ({ ...e, industry: undefined })); }}
          placeholder="Select industry"
        />
        {errors.industry ? <Txt style={styles.err}>{errors.industry}</Txt> : null}
        {isOtherInd ? (
          <>
            <Input testID="pj-industry-other" label="Specify Industry *" value={industryOther} onChangeText={(v) => { setIndustryOther(v); setErrors((e) => ({ ...e, industryOther: undefined })); }} placeholder="Industry name" />
            {errors.industryOther ? <Txt style={styles.err}>{errors.industryOther}</Txt> : null}
          </>
        ) : null}

        <Picker
          testID="pj-category"
          label="Category *"
          options={CATEGORY_OPTIONS}
          value={category}
          onChange={(v) => { setCategory(v as string); setErrors((e) => ({ ...e, category: undefined })); }}
          placeholder="Fresher / Experienced / Intern"
        />
        {errors.category ? <Txt style={styles.err}>{errors.category}</Txt> : null}

        {isExperienced ? (
          <View style={{ flexDirection: "row", gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Picker
                testID="pj-exp-min"
                label="Min Experience *"
                options={EXP_FILTER_OPTIONS}
                value={expMin}
                onChange={(v) => { setExpMin(v as string); setErrors((e) => ({ ...e, expMin: undefined })); }}
                placeholder="0"
              />
              {errors.expMin ? <Txt style={styles.err}>{errors.expMin}</Txt> : null}
            </View>
            <View style={{ flex: 1 }}>
              <Picker
                testID="pj-exp-max"
                label="Max Experience *"
                options={EXP_FILTER_OPTIONS}
                value={expMax}
                onChange={(v) => { setExpMax(v as string); setErrors((e) => ({ ...e, expMax: undefined })); }}
                placeholder="15+"
              />
              {errors.expMax ? <Txt style={styles.err}>{errors.expMax}</Txt> : null}
            </View>
          </View>
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
