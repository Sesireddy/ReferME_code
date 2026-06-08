import React, { useEffect, useState, useCallback } from "react";
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

const MAX_RESUME_BYTES = 5 * 1024 * 1024;

const EDUCATION_OPTIONS = [
  { value: "B.Tech", label: "B.Tech" },
  { value: "Degree", label: "Degree (B.A / B.Com / B.Sc)" },
  { value: "M.Tech", label: "M.Tech" },
  { value: "MBA", label: "MBA" },
  { value: "Others", label: "Others" },
];

const PREFERRED_ROLE_OPTIONS = [
  { value: "fresher", label: "Fresher" },
  { value: "experienced", label: "Experienced" },
];

const RESUME_TABS = [
  { id: "file", label: "Upload file" },
  { id: "link", label: "Paste link" },
] as const;

type ResumeTab = (typeof RESUME_TABS)[number]["id"];

export default function StudentProfile() {
  const router = useRouter();
  const [signoutOpen, setSignoutOpen] = useState(false);
  const [user, setUser] = useState<any>(null);

  // Form state
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [education, setEducation] = useState<string | null>(null);
  const [educationDetails, setEducationDetails] = useState("");
  const [passedOutYear, setPassedOutYear] = useState("");
  const [currentLocation, setCurrentLocation] = useState("");
  const [dob, setDob] = useState("");
  const [preferredRole, setPreferredRole] = useState<string | null>(null);
  const [yearsExp, setYearsExp] = useState("");
  const [skills, setSkills] = useState("");

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
      setEducation(p.education || null);
      setEducationDetails(p.education_details || "");
      setPassedOutYear(p.passed_out_year ? String(p.passed_out_year) : "");
      setCurrentLocation(p.current_location || "");
      setDob(p.dob || "");
      setPreferredRole(p.preferred_role || null);
      setYearsExp(p.years_of_experience ? String(p.years_of_experience) : "");
      setSkills((p.skills || []).join(", "));
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

  async function save() {
    if (!education) return Alert.alert("Missing", "Select your education.");
    if (education === "Others" && !educationDetails.trim()) return Alert.alert("Missing", "Enter your education details.");
    if (!preferredRole) return Alert.alert("Missing", "Select your preferred role.");
    if (preferredRole === "experienced" && !yearsExp) return Alert.alert("Missing", "Enter your years of experience.");
    setSaving(true);
    try {
      const res = await api<any>("/profile", {
        method: "PUT",
        body: {
          name,
          phone,
          education,
          education_details: education === "Others" ? educationDetails : null,
          passed_out_year: passedOutYear ? parseInt(passedOutYear, 10) : null,
          current_location: currentLocation || null,
          dob: dob || null,
          preferred_role: preferredRole,
          years_of_experience: preferredRole === "experienced" ? parseInt(yearsExp || "0", 10) : null,
          skills: skills.split(",").map((s) => s.trim()).filter(Boolean),
          resume_base64: resumeTab === "file" ? (resumeBase64 || null) : null,
          resume_filename: resumeTab === "file" ? (resumeName || null) : null,
          resume_size: resumeTab === "file" ? (resumeSize || null) : null,
          resume_mime_type: resumeTab === "file" ? (resumeMime || null) : null,
          resume_link: resumeTab === "link" ? (resumeLink || null) : null,
        },
      });
      // Merge fresh profile (with new resume_score) back onto user so the header re-renders
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
        <Input testID="profile-name" label="Full name" value={name} onChangeText={setName} placeholder="Your name" />
        <Input testID="profile-phone" label="Mobile number" value={phone} onChangeText={setPhone} placeholder="+91 98765 43210" keyboardType="phone-pad" />

        <Picker
          testID="profile-education"
          label="Education"
          placeholder="Select highest education"
          options={EDUCATION_OPTIONS}
          value={education}
          onChange={(v) => setEducation(v as string)}
        />

        {education === "Others" ? (
          <Input
            testID="profile-education-details"
            label="Education details"
            placeholder="e.g. PG Diploma in Data Science"
            value={educationDetails}
            onChangeText={setEducationDetails}
          />
        ) : null}

        <Input testID="profile-passed-out" label="Passed out year" placeholder="2026" keyboardType="number-pad" maxLength={4} value={passedOutYear} onChangeText={setPassedOutYear} />
        <Input testID="profile-location" label="Current location" placeholder="Bengaluru" value={currentLocation} onChangeText={setCurrentLocation} />
        <Input testID="profile-dob" label="Date of birth" placeholder="YYYY-MM-DD" value={dob} onChangeText={setDob} />

        <Picker
          testID="profile-preferred-role"
          label="Preferred role"
          placeholder="Fresher or experienced?"
          options={PREFERRED_ROLE_OPTIONS}
          value={preferredRole}
          onChange={(v) => setPreferredRole(v as string)}
        />

        {preferredRole === "experienced" ? (
          <Input testID="profile-years-exp" label="Years of experience" placeholder="3" keyboardType="number-pad" value={yearsExp} onChangeText={setYearsExp} />
        ) : null}

        <Input testID="profile-skills" label="Skills (comma-separated)" value={skills} onChangeText={setSkills} placeholder="React, Python, ML" />

        <Txt variant="label" style={{ marginTop: 4, marginBottom: 8 }}>Resume</Txt>
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
