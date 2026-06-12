import React, { useEffect, useState, useCallback, useMemo } from "react";
import { View, StyleSheet, Alert, TouchableOpacity, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import * as DocumentPicker from "expo-document-picker";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { Picker } from "@/src/components/Picker";
import { colors, radius } from "@/src/theme/tokens";
import { api, clearSession } from "@/src/lib/api";
import { ConfirmDialog } from "@/src/components/ConfirmDialog";
import {
  EDUCATION_OPTIONS,
  GENDER_OPTIONS,
  EXPERIENCE_OPTIONS,
  LOCATION_OPTIONS,
  PREFERRED_ROLE_OPTIONS,
  CURRENTLY_WORKING_OPTIONS,
  NOTICE_PERIOD_OPTIONS,
  ANNUAL_SALARY_OPTIONS,
  MONTHS,
  YEARS_2010_2030,
} from "@/src/lib/constants";

const MAX_RESUME_BYTES = 5 * 1024 * 1024;

// DOB ranges: 1950 → (current year - 14). Each as YYYY string.
const CURRENT_YEAR = new Date().getFullYear();
const DOB_YEARS = Array.from({ length: CURRENT_YEAR - 14 - 1950 + 1 }, (_, i) => {
  const y = String(CURRENT_YEAR - 14 - i);
  return { value: y, label: y };
});
const DAYS_31 = Array.from({ length: 31 }, (_, i) => {
  const d = String(i + 1).padStart(2, "0");
  return { value: d, label: d };
});
// Passed-out year: 1990 → current year + 4 (future grads)
const PASSED_OUT_YEARS = Array.from({ length: CURRENT_YEAR + 4 - 1990 + 1 }, (_, i) => {
  const y = String(CURRENT_YEAR + 4 - i);
  return { value: y, label: y };
});

const RESUME_TABS = [
  { id: "file", label: "Upload file" },
  { id: "link", label: "Paste link" },
] as const;

type ResumeTab = (typeof RESUME_TABS)[number]["id"];

export default function StudentProfile() {
  const router = useRouter();
  const [signoutOpen, setSignoutOpen] = useState(false);
  const [user, setUser] = useState<any>(null);

  // Form state — Personal
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [gender, setGender] = useState<string | null>(null);
  const [dobDay, setDobDay] = useState<string | null>(null);
  const [dobMonth, setDobMonth] = useState<string | null>(null);
  const [dobYear, setDobYear] = useState<string | null>(null);
  // Education
  const [education, setEducation] = useState<string | null>(null);
  const [educationDetails, setEducationDetails] = useState("");
  const [passedOutYear, setPassedOutYear] = useState<string | null>(null);
  // Role / Experience
  const [preferredRole, setPreferredRole] = useState<string | null>(null);
  const [yearsExp, setYearsExp] = useState<string | null>(null);
  const [currentLocation, setCurrentLocation] = useState<string | null>(null);
  const [currentLocationOther, setCurrentLocationOther] = useState("");
  const [skills, setSkills] = useState("");
  // Current employment (optional / experienced-only mandatory)
  const [company, setCompany] = useState("");
  const [designation, setDesignation] = useState("");
  const [currentlyWorking, setCurrentlyWorking] = useState<string | null>(null);
  const [workingFromYear, setWorkingFromYear] = useState<string | null>(null);
  const [workingFromMonth, setWorkingFromMonth] = useState<string | null>(null);
  const [workingToYear, setWorkingToYear] = useState<string | null>(null);
  const [workingToMonth, setWorkingToMonth] = useState<string | null>(null);
  const [noticePeriod, setNoticePeriod] = useState<string | null>(null);
  const [annualSalary, setAnnualSalary] = useState<string | null>(null);

  // Missing-fields dialog
  const [missingDialog, setMissingDialog] = useState<{ open: boolean; items: string[] }>({ open: false, items: [] });

  // Resume state
  const [resumeTab, setResumeTab] = useState<ResumeTab>("file");
  const [resumeBase64, setResumeBase64] = useState("");
  const [resumeName, setResumeName] = useState("");
  const [resumeSize, setResumeSize] = useState(0);
  const [resumeMime, setResumeMime] = useState("");
  const [resumeLink, setResumeLink] = useState("");

  const [saving, setSaving] = useState(false);
  const [picking, setPicking] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Wallet
  const [wallet, setWallet] = useState<{ credits: number; free_uses_left: number; total_deposits: number; transactions: any[] }>({
    credits: 0,
    free_uses_left: 0,
    total_deposits: 0,
    transactions: [],
  });

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [me, w] = await Promise.all([
        api<{ user: any; profile: any }>("/auth/me"),
        api<any>("/wallet"),
      ]);
      setUser({ ...me.user, profile: me.profile || {} });
      setName(me.user.name || "");
      const p = me.profile || {};
      setPhone(p.phone || "");
      setGender(p.gender || null);
      setEducation(p.education || null);
      setEducationDetails(p.education_details || "");
      setPassedOutYear(p.passed_out_year ? String(p.passed_out_year) : null);
      // Location: if existing value is in LOCATION_OPTIONS, set it; otherwise treat as Other.
      const loc = p.current_location || "";
      if (loc) {
        const isStd = LOCATION_OPTIONS.some((o) => o.value === loc);
        if (isStd) {
          setCurrentLocation(loc);
          setCurrentLocationOther("");
        } else {
          setCurrentLocation("__OTHER__");
          setCurrentLocationOther(loc);
        }
      } else {
        setCurrentLocation(null);
        setCurrentLocationOther("");
      }
      // DOB: split YYYY-MM-DD into 3 pickers
      if (p.dob && /^\d{4}-\d{2}-\d{2}$/.test(p.dob)) {
        const [yy, mm, dd] = p.dob.split("-");
        setDobYear(yy);
        setDobMonth(mm);
        setDobDay(dd);
      } else {
        setDobDay(null); setDobMonth(null); setDobYear(null);
      }
      setPreferredRole(p.preferred_role || null);
      setYearsExp(p.years_of_experience !== undefined && p.years_of_experience !== null ? String(p.years_of_experience) : null);
      setSkills((p.skills || []).join(", "));
      setCompany(p.company || "");
      setDesignation(p.designation || "");
      setCurrentlyWorking(p.currently_working || null);
      setWorkingFromYear(p.working_since_from_year || null);
      setWorkingFromMonth(p.working_since_from_month || null);
      setWorkingToYear(p.working_since_to_year || null);
      setWorkingToMonth(p.working_since_to_month || null);
      setNoticePeriod(p.notice_period || null);
      setAnnualSalary(p.annual_salary || null);
      setResumeBase64(p.resume_base64 || "");
      setResumeName(p.resume_filename || "");
      setResumeSize(p.resume_size || 0);
      setResumeMime(p.resume_mime_type || "");
      setResumeLink(p.resume_link || "");
      if (!p.resume_base64 && p.resume_link) setResumeTab("link");
      setWallet(w);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function pickResume() {
    setPicking(true);
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: [
          "application/pdf",
          "application/msword", // .doc
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document", // .docx
        ],
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (res.canceled || !res.assets?.length) return;
      const file = res.assets[0];
      if (file.size && file.size > MAX_RESUME_BYTES) {
        Alert.alert("File too large", "Resume must be under 5 MB.");
        return;
      }
      const response = await fetch(file.uri);
      const blob = await response.blob();
      const base64: string = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => {
          const r = reader.result as string;
          resolve(r.includes(",") ? r.split(",")[1] : r);
        };
        reader.onerror = () => reject(new Error("Read failed"));
        reader.readAsDataURL(blob);
      });
      setResumeBase64(base64);
      setResumeName(file.name);
      setResumeSize(file.size || blob.size || 0);
      setResumeMime(file.mimeType || blob.type || "");
      setResumeLink(""); // clear link if a file is picked
    } catch (e: any) {
      Alert.alert("Could not pick file", e.message || String(e));
    } finally {
      setPicking(false);
    }
  }

  function clearResumeFile() {
    setResumeBase64("");
    setResumeName("");
    setResumeSize(0);
    setResumeMime("");
  }

  // Composed DOB string (YYYY-MM-DD) if all 3 parts selected
  const dobIso = useMemo(() => {
    if (dobYear && dobMonth && dobDay) return `${dobYear}-${dobMonth}-${dobDay}`;
    return "";
  }, [dobYear, dobMonth, dobDay]);

  // Resolved location string (handles "Other -> custom")
  const resolvedLocation = useMemo(() => {
    if (currentLocation === "__OTHER__") return currentLocationOther.trim();
    return currentLocation || "";
  }, [currentLocation, currentLocationOther]);

  function collectMissing(): string[] {
    const missing: string[] = [];
    if (!name.trim()) missing.push("Full Name");
    if (!gender) missing.push("Gender");
    if (!dobIso) missing.push("Date of Birth");
    if (!phone.trim()) missing.push("Mobile Number");
    if (!education) missing.push("Education");
    if (education === "__OTHER__" && !educationDetails.trim()) missing.push("Education Details");
    if (!passedOutYear) missing.push("Passed Out Year");
    if (!preferredRole) missing.push("Preferred Role");
    if (!resolvedLocation) missing.push("Current Location");
    if (!skills.trim()) missing.push("Skill Set");
    // Experienced-only mandatory fields
    if (preferredRole === "experienced") {
      if (yearsExp === null || yearsExp === "") missing.push("Years of Experience");
      if (!company.trim()) missing.push("Company Name");
      if (!designation.trim()) missing.push("Designation");
      if (!currentlyWorking) missing.push("Currently Working");
      if (!workingFromYear || !workingFromMonth) missing.push("Working Since (From)");
      if (currentlyWorking === "no" && (!workingToYear || !workingToMonth)) missing.push("Working Since (To)");
      if (currentlyWorking === "yes" && !noticePeriod) missing.push("Notice Period");
      if (!annualSalary) missing.push("Annual Salary (CTC)");
    }
    const hasResume = (resumeTab === "file" && !!resumeBase64) || (resumeTab === "link" && !!resumeLink.trim());
    if (!hasResume) missing.push("Resume (upload or link)");
    return missing;
  }

  async function save() {
    const missing = collectMissing();
    if (missing.length > 0) {
      setMissingDialog({ open: true, items: missing });
      return;
    }
    setSaving(true);
    try {
      const isExp = preferredRole === "experienced";
      const yoeNum = !isExp ? 0 : (yearsExp === "30+" ? 30 : parseInt(yearsExp || "0", 10));
      const res = await api<any>("/profile", {
        method: "PUT",
        body: {
          name,
          phone,
          gender,
          education,
          education_details: education === "__OTHER__" ? educationDetails : null,
          passed_out_year: passedOutYear ? parseInt(passedOutYear, 10) : null,
          current_location: resolvedLocation || null,
          dob: dobIso || null,
          preferred_role: preferredRole,
          years_of_experience: yoeNum,
          skills: skills.split(",").map((s) => s.trim()).filter(Boolean),
          // Experienced-only fields (null otherwise so server overrides stale values)
          company: isExp ? company || null : null,
          designation: isExp ? designation || null : null,
          currently_working: isExp ? currentlyWorking : null,
          working_since_from_year: isExp ? workingFromYear : null,
          working_since_from_month: isExp ? workingFromMonth : null,
          working_since_to_year: isExp && currentlyWorking === "no" ? workingToYear : null,
          working_since_to_month: isExp && currentlyWorking === "no" ? workingToMonth : null,
          notice_period: isExp && currentlyWorking === "yes" ? noticePeriod : null,
          annual_salary: isExp ? annualSalary : null,
          resume_base64: resumeTab === "file" ? (resumeBase64 || null) : null,
          resume_filename: resumeTab === "file" ? (resumeName || null) : null,
          resume_size: resumeTab === "file" ? (resumeSize || null) : null,
          resume_mime_type: resumeTab === "file" ? (resumeMime || null) : null,
          resume_link: resumeTab === "link" ? (resumeLink || null) : null,
        },
      });
      setUser((prev: any) => ({ ...(prev || {}), ...res.user, profile: res.profile || {} }));
      Alert.alert("Saved", res.user.profile_complete ? "Profile complete!" : "Almost there. Fill any missing fields.");
    } catch (e: any) {
      Alert.alert("Save failed", e.message);
    } finally {
      setSaving(false);
    }
  }

  async function logout() {
    setSignoutOpen(true);
  }
  async function confirmLogout() {
    setSignoutOpen(false);
    await clearSession();
    router.replace("/welcome");
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <Txt variant="h1">Profile</Txt>
        <TouchableOpacity testID="logout-btn" onPress={logout}>
          <Ionicons name="log-out-outline" size={24} color={colors.textPrimary} />
        </TouchableOpacity>
      </View>

      <Card style={{ marginTop: 16 }}>
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          <View style={{ flex: 1 }}>
            <Txt variant="label">Email</Txt>
            <Txt variant="h3">{user?.email}</Txt>
          </View>
          <View style={{ alignItems: "flex-end" }}>
            <Txt variant="label" style={{ color: colors.primary }}>Resume score</Txt>
            <Txt variant="h2" testID="resume-score">{user?.profile?.resume_score ?? 0}/100</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary }}>auto-updated</Txt>
          </View>
        </View>
        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 8 }}>
          Each completed mock interview boosts your score. Complete the form to add more points.
        </Txt>
      </Card>

      {/* ----------------- Wallet section ----------------- */}
      <LinearGradient
        colors={["#FF5A5F", "#FFB347"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.walletCard}
      >
        <View style={styles.walletHead}>
          <View style={styles.walletIcon}>
            <Ionicons name="wallet" size={24} color="#fff" />
          </View>
          <View style={{ flex: 1, marginLeft: 12 }}>
            <Txt style={{ color: "#fff", opacity: 0.85 }} variant="label">Wallet</Txt>
            <Txt style={{ color: "#fff", fontSize: 36, fontWeight: "800", marginTop: 2 }} testID="profile-credits">
              {wallet.credits}
            </Txt>
            <Txt style={{ color: "#fff", opacity: 0.9 }} variant="small">
              credits available · {wallet.free_uses_left} free uses
            </Txt>
          </View>
        </View>
        <Button
          testID="add-credits-btn"
          title="Add credits"
          variant="secondary"
          icon={<Ionicons name="add-circle" size={18} color={colors.textPrimary} />}
          onPress={() => router.push("/student/wallet")}
          style={{ marginTop: 14 }}
        />
      </LinearGradient>

      <WalletHistory transactions={wallet.transactions} />
      {/* --------------- end Wallet section --------------- */}

      <View style={{ marginTop: 16 }}>
        <Txt variant="h3" style={styles.sectionHeader}>Personal Details</Txt>
        <Input testID="profile-name" label="Full name *" value={name} onChangeText={setName} placeholder="Your full name" />

        <Picker
          testID="profile-gender"
          label="Gender *"
          placeholder="Select gender"
          options={GENDER_OPTIONS}
          value={gender}
          onChange={(v) => setGender(v as string)}
        />

        <Txt variant="label" style={{ marginBottom: 6 }}>Date of Birth *</Txt>
        <View style={styles.dobRow}>
          <View style={{ flex: 1.1 }}>
            <Picker
              testID="profile-dob-day"
              placeholder="Day"
              options={DAYS_31}
              value={dobDay}
              onChange={(v) => setDobDay(v as string)}
            />
          </View>
          <View style={{ flex: 1.3 }}>
            <Picker
              testID="profile-dob-month"
              placeholder="Month"
              options={MONTHS}
              value={dobMonth}
              onChange={(v) => setDobMonth(v as string)}
            />
          </View>
          <View style={{ flex: 1.4 }}>
            <Picker
              testID="profile-dob-year"
              placeholder="Year"
              options={DOB_YEARS}
              value={dobYear}
              onChange={(v) => setDobYear(v as string)}
            />
          </View>
        </View>

        <Input testID="profile-phone" label="Mobile number *" value={phone} onChangeText={setPhone} placeholder="+91 98765 43210" keyboardType="phone-pad" />

        <Txt variant="h3" style={styles.sectionHeader}>Education</Txt>
        <Picker
          testID="profile-education"
          label="Education *"
          placeholder="Select highest education"
          options={EDUCATION_OPTIONS}
          value={education}
          onChange={(v) => setEducation(v as string)}
        />

        {education === "__OTHER__" ? (
          <Input
            testID="profile-education-details"
            label="Education details *"
            placeholder="e.g. PG Diploma in Data Science"
            value={educationDetails}
            onChangeText={setEducationDetails}
          />
        ) : null}

        <Picker
          testID="profile-passed-out"
          label="Passed out year *"
          placeholder="Select passing year"
          options={PASSED_OUT_YEARS}
          value={passedOutYear}
          onChange={(v) => setPassedOutYear(v as string)}
        />

        <Txt variant="h3" style={styles.sectionHeader}>Career Information</Txt>
        <Picker
          testID="profile-preferred-role"
          label="Preferred role *"
          placeholder="Fresher / Experienced / Intern"
          options={PREFERRED_ROLE_OPTIONS}
          value={preferredRole}
          onChange={(v) => setPreferredRole(v as string)}
        />

        <Picker
          testID="profile-location"
          label="Current location *"
          placeholder="Select city"
          options={LOCATION_OPTIONS}
          value={currentLocation}
          onChange={(v) => setCurrentLocation(v as string)}
        />
        {currentLocation === "__OTHER__" ? (
          <Input
            testID="profile-location-other"
            label="Specify city *"
            value={currentLocationOther}
            onChangeText={setCurrentLocationOther}
            placeholder="Your city"
          />
        ) : null}

        <Input testID="profile-skills" label="Skills (comma-separated) *" value={skills} onChangeText={setSkills} placeholder="React, Python, ML" />

        {preferredRole === "experienced" ? (
          <>
            <Txt variant="h3" style={styles.sectionHeader}>Experience Details</Txt>

            <Picker
              testID="profile-years-exp"
              label="Years of experience *"
              placeholder="Select years"
              options={EXPERIENCE_OPTIONS}
              value={yearsExp}
              onChange={(v) => setYearsExp(v as string)}
            />

            <Input testID="profile-company" label="Company name *" value={company} onChangeText={setCompany} placeholder="e.g. Acme Corp" />
            <Input testID="profile-designation" label="Designation *" value={designation} onChangeText={setDesignation} placeholder="e.g. Software Engineer" />

            <Picker
              testID="profile-currently-working"
              label="Currently working? *"
              placeholder="Select yes / no"
              options={CURRENTLY_WORKING_OPTIONS}
              value={currentlyWorking}
              onChange={(v) => setCurrentlyWorking(v as string)}
            />

            {currentlyWorking ? (
              <>
                <Txt variant="label" style={{ marginBottom: 6, marginTop: 4 }}>Working Since *</Txt>
                <View style={styles.workingSinceRow}>
                  <View style={styles.workingSinceCol}>
                    <Txt variant="small" style={styles.smallLabel}>From</Txt>
                    <View style={styles.dobRow}>
                      <View style={{ flex: 1 }}>
                        <Picker
                          testID="profile-working-from-month"
                          placeholder="Month"
                          options={MONTHS}
                          value={workingFromMonth}
                          onChange={(v) => setWorkingFromMonth(v as string)}
                        />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Picker
                          testID="profile-working-from-year"
                          placeholder="Year"
                          options={YEARS_2010_2030}
                          value={workingFromYear}
                          onChange={(v) => setWorkingFromYear(v as string)}
                        />
                      </View>
                    </View>
                  </View>
                  <View style={styles.workingSinceCol}>
                    <Txt variant="small" style={styles.smallLabel}>To</Txt>
                    {currentlyWorking === "yes" ? (
                      <View style={styles.presentBox} testID="profile-working-to-present">
                        <Txt variant="body" style={{ color: colors.primary }}>Present</Txt>
                      </View>
                    ) : (
                      <View style={styles.dobRow}>
                        <View style={{ flex: 1 }}>
                          <Picker
                            testID="profile-working-to-month"
                            placeholder="Month"
                            options={MONTHS}
                            value={workingToMonth}
                            onChange={(v) => setWorkingToMonth(v as string)}
                          />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Picker
                            testID="profile-working-to-year"
                            placeholder="Year"
                            options={YEARS_2010_2030}
                            value={workingToYear}
                            onChange={(v) => setWorkingToYear(v as string)}
                          />
                        </View>
                      </View>
                    )}
                  </View>
                </View>
              </>
            ) : null}

            {currentlyWorking === "yes" ? (
              <Picker
                testID="profile-notice-period"
                label="Notice period *"
                placeholder="Select notice period"
                options={NOTICE_PERIOD_OPTIONS}
                value={noticePeriod}
                onChange={(v) => setNoticePeriod(v as string)}
              />
            ) : null}

            <Picker
              testID="profile-annual-salary"
              label="Annual salary (CTC) *"
              placeholder="Select CTC range"
              options={ANNUAL_SALARY_OPTIONS}
              value={annualSalary}
              onChange={(v) => setAnnualSalary(v as string)}
            />
          </>
        ) : null}

        <Txt variant="h3" style={styles.sectionHeader}>Resume *</Txt>
        <View style={styles.tabs}>
          {RESUME_TABS.map((t) => {
            const active = resumeTab === t.id;
            return (
              <TouchableOpacity
                key={t.id}
                testID={`resume-tab-${t.id}`}
                onPress={() => setResumeTab(t.id)}
                style={[styles.tab, active && styles.tabActive]}
              >
                <Txt style={{ fontWeight: "700", color: active ? "#fff" : colors.textPrimary }}>{t.label}</Txt>
              </TouchableOpacity>
            );
          })}
        </View>

        {resumeTab === "file" ? (
          resumeBase64 ? (
            <View testID="resume-picked" style={styles.fileBox}>
              <View style={styles.fileIcon}>
                <Ionicons name="document-text" size={22} color={colors.primary} />
              </View>
              <View style={{ flex: 1, marginLeft: 10 }}>
                <Txt style={{ fontWeight: "600" }} numberOfLines={1}>{resumeName || "Resume"}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>
                  {resumeSize ? `${(resumeSize / 1024).toFixed(0)} KB` : "uploaded"} · {resumeMime?.includes("word") ? "Word" : "PDF"}
                </Txt>
              </View>
              <TouchableOpacity testID="resume-replace" onPress={pickResume} hitSlop={10} style={{ marginRight: 10 }}>
                <Ionicons name="refresh" size={20} color={colors.textSecondary} />
              </TouchableOpacity>
              <TouchableOpacity testID="resume-remove" onPress={clearResumeFile} hitSlop={10}>
                <Ionicons name="close-circle" size={22} color={colors.error} />
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity testID="resume-pick" onPress={pickResume} activeOpacity={0.85} disabled={picking}>
              <View style={[styles.fileBox, styles.fileBoxEmpty]}>
                {picking ? (
                  <ActivityIndicator color={colors.primary} />
                ) : (
                  <>
                    <Ionicons name="cloud-upload-outline" size={22} color={colors.primary} />
                    <Txt style={{ marginLeft: 10, fontWeight: "600", color: colors.primary }}>Upload resume (PDF / Word · max 5MB)</Txt>
                  </>
                )}
              </View>
            </TouchableOpacity>
          )
        ) : (
          <Input
            testID="resume-link"
            label=""
            placeholder="https://drive.google.com/... or LinkedIn URL"
            value={resumeLink}
            onChangeText={setResumeLink}
            autoCapitalize="none"
            keyboardType="url"
          />
        )}

        <View style={{ height: 14 }} />
        <Button testID="save-profile" title="Save profile" onPress={save} loading={saving} />
      </View>

      <Card style={{ marginTop: 16, backgroundColor: "#FFF4E0" }}>
        <Txt variant="h3">Need help?</Txt>
        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>Reach out via support if anything looks wrong.</Txt>
        <Button testID="raise-dispute" title="Raise a dispute" variant="outline" style={{ marginTop: 12 }} onPress={() => router.push("/notifications")} />
      </Card>

      <View style={{ marginTop: 24, marginBottom: 32 }}>
        <Button
          testID="sign-out-btn"
          title="Sign Out"
          variant="outline"
          onPress={logout}
          style={{ borderColor: colors.error }}
        />
      </View>

      <ConfirmDialog
        visible={signoutOpen}
        title="Are you sure you want to sign out?"
        confirmLabel="Yes, Sign Out"
        cancelLabel="Cancel"
        destructive
        onCancel={() => setSignoutOpen(false)}
        onConfirm={confirmLogout}
      />

      <ConfirmDialog
        visible={missingDialog.open}
        title="Please complete your profile"
        message={`The following fields are still missing:\n\n• ${missingDialog.items.join("\n• ")}`}
        confirmLabel="Got it"
        cancelLabel="Close"
        onCancel={() => setMissingDialog({ open: false, items: [] })}
        onConfirm={() => setMissingDialog({ open: false, items: [] })}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  walletCard: { marginTop: 16, padding: 18, borderRadius: radius.xxl },
  walletHead: { flexDirection: "row", alignItems: "center" },
  walletIcon: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,255,255,0.2)" },
  historyHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 22, marginBottom: 8 },
  historyTabs: { flexDirection: "row", backgroundColor: colors.surfaceAlt, borderRadius: 999, padding: 4, marginBottom: 12 },
  historyTab: { flex: 1, paddingVertical: 8, alignItems: "center", borderRadius: 999 },
  historyTabActive: { backgroundColor: colors.primary },
  tabs: { flexDirection: "row", backgroundColor: colors.surfaceAlt, borderRadius: 999, padding: 4, marginBottom: 12 },
  tab: { flex: 1, paddingVertical: 8, alignItems: "center", borderRadius: 999 },
  tabActive: { backgroundColor: colors.primary },
  sectionHeader: { marginTop: 18, marginBottom: 8, color: colors.primary },
  dobRow: { flexDirection: "row", gap: 8 },
  workingSinceRow: { flexDirection: "row", gap: 12, marginBottom: 6 },
  workingSinceCol: { flex: 1 },
  smallLabel: { marginBottom: 4, color: colors.textSecondary, fontWeight: "600" },
  presentBox: {
    height: 48,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.primary,
    backgroundColor: "#FFF5F5",
    alignItems: "center",
    justifyContent: "center",
  },
  fileBox: {
    flexDirection: "row",
    alignItems: "center",
    padding: 14,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceAlt,
    borderWidth: 2,
    borderColor: "transparent",
  },
  fileBoxEmpty: {
    borderStyle: "dashed",
    borderColor: colors.primary,
    backgroundColor: "#FFF5F5",
    justifyContent: "center",
  },
  fileIcon: {
    width: 40, height: 40, borderRadius: 10, alignItems: "center", justifyContent: "center", backgroundColor: "#FFE4E5",
  },
});

function WalletHistory({ transactions }: { transactions: any[] }) {
  const [expanded, setExpanded] = useState(false);
  const [filter, setFilter] = useState<"all" | "purchase" | "usage">("all");
  const purchases = transactions.filter((t) => t.delta > 0 && (t.reason || "").toLowerCase().includes("deposit"));
  const usage = transactions.filter((t) => t.delta < 0);
  const all = transactions;
  const shown = filter === "purchase" ? purchases : filter === "usage" ? usage : all;

  return (
    <View>
      <TouchableOpacity
        testID="credit-history-toggle"
        activeOpacity={0.85}
        onPress={() => setExpanded((p) => !p)}
        style={styles.historyHeader}
      >
        <Txt variant="h3">Credit History</Txt>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Txt variant="small" style={{ color: colors.textSecondary }}>{transactions.length} entries</Txt>
          <Ionicons name={expanded ? "chevron-up" : "chevron-down"} size={20} color={colors.textSecondary} />
        </View>
      </TouchableOpacity>
      {!expanded ? null : (
        <>
          <View style={styles.historyTabs}>
        {([
          { id: "all" as const, label: "All" },
          { id: "purchase" as const, label: "Purchases" },
          { id: "usage" as const, label: "Usage" },
        ]).map((t) => (
          <TouchableOpacity
            key={t.id}
            testID={`history-tab-${t.id}`}
            onPress={() => setFilter(t.id)}
            style={[styles.historyTab, filter === t.id && styles.historyTabActive]}
          >
            <Txt style={{ fontWeight: "700", color: filter === t.id ? "#fff" : colors.textPrimary, fontSize: 13 }}>
              {t.label} ({t.id === "all" ? all.length : t.id === "purchase" ? purchases.length : usage.length})
            </Txt>
          </TouchableOpacity>
        ))}
      </View>
      <View style={{ gap: 6 }}>
        {shown.length === 0 ? <Txt variant="muted">No matching entries.</Txt> : null}
        {shown.slice(0, 20).map((t) => (
          <Card key={t.id} padding={12}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <View style={{ flex: 1 }}>
                <Txt style={{ fontWeight: "600", textTransform: "capitalize" }}>{(t.reason || "").replace(/_/g, " ")}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>{new Date(t.created_at).toLocaleString()}</Txt>
              </View>
              <Txt style={{ fontWeight: "800", color: t.delta >= 0 ? colors.success : colors.error }}>
                {t.delta >= 0 ? "+" : ""}{t.delta}
              </Txt>
            </View>
          </Card>
        ))}
      </View>
        </>
      )}
    </View>
  );
}
