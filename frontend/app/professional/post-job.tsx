import React, { useState } from "react";
import { View, Alert, StyleSheet, TouchableOpacity, Image } from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as DocumentPicker from "expo-document-picker";
import { Ionicons } from "@expo/vector-icons";
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
  ...Array.from({ length: 20 }, (_, i) => ({ value: String(i + 1), label: String(i + 1) })),
  { value: "20+", label: "20+" },
  { value: "50+", label: "50+" },
  { value: "100+", label: "100+" },
  { value: "500+", label: "500+" },
  { value: "1000+", label: "1000+" },
];

type Errors = Partial<Record<
  "title" | "company" | "desc" | "location" | "locationOther" | "salary" | "industry" |
  "industryOther" | "category" | "skills" | "openings" | "expMin" | "expMax" | "proof",
  string
>>;

function isValidUrl(u: string): boolean {
  return /^https?:\/\/[^\s]+\.[^\s]+/i.test((u || "").trim());
}

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
  const [openings, setOpenings] = useState<string | null>(null);
  // Proof of opening fields
  const [proofLink, setProofLink] = useState("");
  const [proofDataUri, setProofDataUri] = useState<string>("");
  const [proofMime, setProofMime] = useState<string>("");
  const [proofFileName, setProofFileName] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [success, setSuccess] = useState(false);

  async function pickImage() {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (perm.status !== "granted") return Alert.alert("Permission needed", "Please allow gallery access.");
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: false,
      quality: 0.7,
      base64: true,
    });
    if (res.canceled || !res.assets?.[0]) return;
    const a = res.assets[0];
    const mime = a.mimeType || "image/jpeg";
    if (!["image/jpeg", "image/jpg", "image/png"].includes(mime)) {
      return Alert.alert("Unsupported format", "Please upload a JPG, JPEG or PNG image.");
    }
    setProofDataUri(`data:${mime};base64,${a.base64}`);
    setProofMime(mime);
    setProofFileName(a.fileName || `screenshot.${mime.split("/")[1] || "jpg"}`);
    setErrors((e) => ({ ...e, proof: undefined }));
  }

  async function pickPdf() {
    const res = await DocumentPicker.getDocumentAsync({ type: ["application/pdf"], copyToCacheDirectory: true });
    if (res.canceled || !res.assets?.[0]) return;
    const a = res.assets[0];
    try {
      // Read as base64
      const FileSystem = await import("expo-file-system/legacy");
      const base64 = await (FileSystem as any).readAsStringAsync(a.uri, { encoding: "base64" });
      setProofDataUri(`data:application/pdf;base64,${base64}`);
      setProofMime("application/pdf");
      setProofFileName(a.name || "proof.pdf");
      setErrors((e) => ({ ...e, proof: undefined }));
    } catch (e: any) {
      Alert.alert("Read failed", "Could not read PDF file.");
    }
  }

  function clearProof() {
    setProofDataUri("");
    setProofMime("");
    setProofFileName("");
  }

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
    // Proof of opening — at least one required
    if (!proofDataUri && !proofLink.trim()) {
      e.proof = "Please provide either a Job Opening Screenshot or a Job Opening Link to verify the position.";
    } else if (proofLink.trim() && !isValidUrl(proofLink)) {
      e.proof = "Please enter a valid Job Opening Link (must start with http:// or https://).";
    }
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
          proof_link: proofLink.trim() || null,
          proof_screenshot_b64: proofDataUri || null,
          proof_screenshot_mime: proofMime || null,
        },
      });
      setSuccess(true);
      // Reset
      setTitle(""); setCompany(""); setDesc(""); setLocation(null); setLocationOther("");
      setSalaryRange(null); setIndustry(null); setIndustryOther("");
      setCategory("fresher"); setExpMin(null); setExpMax(null);
      setSkills(""); setOpenings(null);
      setProofLink(""); clearProof();
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
        title="Submitted for Review"
        message="Your job has been submitted for review and is awaiting Admin approval. You will be notified once it is approved."
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
          placeholder="Select Number of Open Positions"
        />
        {errors.openings ? <Txt style={styles.err}>{errors.openings}</Txt> : null}

        {/* Proof of opening — required */}
        <View style={styles.proofBox}>
          <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 6 }}>
            <Ionicons name="shield-checkmark" size={18} color="#7C3AED" />
            <Txt style={styles.proofTitle}>Proof of Job Opening *</Txt>
          </View>
          <Txt variant="small" style={{ color: colors.textSecondary, marginBottom: 10 }}>
            To verify this position is genuine, please share either a screenshot (JPG/PNG/PDF) OR a link to the job posting.
          </Txt>

          {/* Screenshot upload area */}
          {proofDataUri ? (
            <View style={styles.proofPreview}>
              {proofMime === "application/pdf" ? (
                <View style={{ flexDirection: "row", alignItems: "center", flex: 1 }}>
                  <Ionicons name="document-text" size={32} color={colors.error} />
                  <Txt style={{ marginLeft: 10, flex: 1 }} numberOfLines={1}>{proofFileName}</Txt>
                </View>
              ) : (
                <Image source={{ uri: proofDataUri }} style={{ width: 70, height: 70, borderRadius: 8 }} />
              )}
              <TouchableOpacity testID="proof-remove" onPress={clearProof} hitSlop={8} style={{ marginLeft: 8 }}>
                <Ionicons name="close-circle" size={22} color={colors.error} />
              </TouchableOpacity>
            </View>
          ) : (
            <View style={{ flexDirection: "row", gap: 8 }}>
              <TouchableOpacity testID="proof-pick-image" onPress={pickImage} style={[styles.proofBtn, { borderColor: colors.primary }]}>
                <Ionicons name="image" size={18} color={colors.primary} />
                <Txt style={{ marginLeft: 6, color: colors.primary, fontWeight: "600" }}>Upload Image</Txt>
              </TouchableOpacity>
              <TouchableOpacity testID="proof-pick-pdf" onPress={pickPdf} style={[styles.proofBtn, { borderColor: colors.error }]}>
                <Ionicons name="document" size={18} color={colors.error} />
                <Txt style={{ marginLeft: 6, color: colors.error, fontWeight: "600" }}>Upload PDF</Txt>
              </TouchableOpacity>
            </View>
          )}

          <View style={{ flexDirection: "row", alignItems: "center", marginVertical: 10 }}>
            <View style={{ flex: 1, height: 1, backgroundColor: colors.border }} />
            <Txt variant="small" style={{ color: colors.textSecondary, marginHorizontal: 8 }}>OR</Txt>
            <View style={{ flex: 1, height: 1, backgroundColor: colors.border }} />
          </View>

          <Input
            testID="proof-link"
            label="Job Opening Link"
            placeholder="https://careers.company.com/job/123"
            value={proofLink}
            onChangeText={(v) => { setProofLink(v); setErrors((e) => ({ ...e, proof: undefined })); }}
            autoCapitalize="none"
            keyboardType="url"
          />
          {errors.proof ? <Txt style={[styles.err, { marginTop: 0 }]}>{errors.proof}</Txt> : null}
        </View>

        <Button testID="pj-submit" title="Post job" loading={busy} onPress={post} style={{ marginTop: 8 }} />
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  err: { color: colors.error, fontSize: 12, marginTop: -8, marginBottom: 8 },
  proofBox: {
    marginTop: 10,
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#7C3AED40",
    backgroundColor: "#7C3AED0A",
  },
  proofTitle: { marginLeft: 6, fontWeight: "700", color: "#7C3AED", fontSize: 14 },
  proofBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 12,
    borderRadius: 10,
    borderWidth: 1.5,
    borderStyle: "dashed",
    backgroundColor: "#fff",
  },
  proofPreview: {
    flexDirection: "row",
    alignItems: "center",
    padding: 10,
    backgroundColor: "#fff",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
  },
});
