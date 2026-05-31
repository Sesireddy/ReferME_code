import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Alert, TouchableOpacity, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as DocumentPicker from "expo-document-picker";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors, radius } from "@/src/theme/tokens";
import { api, clearSession } from "@/src/lib/api";

const MAX_RESUME_BYTES = 5 * 1024 * 1024; // 5 MB

export default function StudentProfile() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [name, setName] = useState("");
  const [education, setEducation] = useState("");
  const [skills, setSkills] = useState("");
  const [resumeBase64, setResumeBase64] = useState("");
  const [resumeName, setResumeName] = useState("");
  const [resumeSize, setResumeSize] = useState(0);
  const [score, setScore] = useState("");
  const [saving, setSaving] = useState(false);
  const [picking, setPicking] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const me = await api<{ user: any; profile: any }>("/auth/me");
      setUser(me.user);
      setName(me.user.name || "");
      setEducation(me.profile?.education || "");
      setSkills((me.profile?.skills || []).join(", "));
      setResumeBase64(me.profile?.resume_base64 || "");
      setResumeName(me.profile?.resume_filename || "");
      setResumeSize(me.profile?.resume_size || 0);
      setScore(String(me.profile?.resume_score || ""));
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function pickResume() {
    setPicking(true);
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: ["application/pdf"],
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (res.canceled || !res.assets?.length) return;
      const file = res.assets[0];
      if (file.size && file.size > MAX_RESUME_BYTES) {
        Alert.alert("File too large", "Resume must be under 5 MB.");
        return;
      }
      // Convert to base64 via fetch → blob → FileReader (works on web & native)
      const response = await fetch(file.uri);
      const blob = await response.blob();
      const base64: string = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => {
          const result = reader.result as string;
          // Strip "data:application/pdf;base64,"
          resolve(result.includes(",") ? result.split(",")[1] : result);
        };
        reader.onerror = () => reject(new Error("Read failed"));
        reader.readAsDataURL(blob);
      });
      setResumeBase64(base64);
      setResumeName(file.name);
      setResumeSize(file.size || blob.size || 0);
    } catch (e: any) {
      Alert.alert("Could not pick file", e.message || String(e));
    } finally {
      setPicking(false);
    }
  }

  function clearResume() {
    setResumeBase64("");
    setResumeName("");
    setResumeSize(0);
  }

  async function save() {
    setSaving(true);
    try {
      const res = await api<any>("/profile", {
        method: "PUT",
        body: {
          name,
          education,
          skills: skills.split(",").map((s) => s.trim()).filter(Boolean),
          resume_base64: resumeBase64 || null,
          resume_filename: resumeName || null,
          resume_size: resumeSize || null,
          resume_score: parseInt(score || "0", 10) || 0,
        },
      });
      Alert.alert("Saved", res.user.profile_complete ? "Profile complete!" : "Keep going to complete.");
      setUser(res.user);
    } catch (e: any) {
      Alert.alert("Save failed", e.message);
    } finally {
      setSaving(false);
    }
  }

  async function logout() {
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
        <Txt variant="label">Email</Txt>
        <Txt variant="h3">{user?.email}</Txt>
        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>
          Profile completion: {user?.profile_complete ? "100%" : "in progress"}
        </Txt>
      </Card>

      <View style={{ marginTop: 16 }}>
        <Input testID="profile-name" label="Full name" value={name} onChangeText={setName} placeholder="Your name" />
        <Input testID="profile-education" label="Education" value={education} onChangeText={setEducation} placeholder="B.Tech CS — IIT Delhi, 2026" />
        <Input testID="profile-skills" label="Skills (comma-separated)" value={skills} onChangeText={setSkills} placeholder="React, Python, ML" />

        <Txt variant="label" style={{ marginBottom: 6 }}>Resume (PDF)</Txt>
        {resumeBase64 ? (
          <View testID="resume-picked" style={styles.fileBox}>
            <View style={styles.fileIcon}>
              <Ionicons name="document-text" size={22} color={colors.primary} />
            </View>
            <View style={{ flex: 1, marginLeft: 10 }}>
              <Txt style={{ fontWeight: "600" }} numberOfLines={1}>{resumeName || "Resume.pdf"}</Txt>
              <Txt variant="small" style={{ color: colors.textSecondary }}>
                {resumeSize ? `${(resumeSize / 1024).toFixed(0)} KB` : "uploaded"}
              </Txt>
            </View>
            <TouchableOpacity testID="resume-replace" onPress={pickResume} hitSlop={10} style={{ marginRight: 10 }}>
              <Ionicons name="refresh" size={20} color={colors.textSecondary} />
            </TouchableOpacity>
            <TouchableOpacity testID="resume-remove" onPress={clearResume} hitSlop={10}>
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
                  <Txt style={{ marginLeft: 10, fontWeight: "600", color: colors.primary }}>Upload resume (PDF · max 5MB)</Txt>
                </>
              )}
            </View>
          </TouchableOpacity>
        )}
        <View style={{ height: 14 }} />

        <Input testID="profile-score" label="Resume score (0-100)" value={score} onChangeText={setScore} keyboardType="number-pad" />
        <Button testID="save-profile" title="Save profile" onPress={save} loading={saving} />
      </View>

      <Card style={{ marginTop: 16, backgroundColor: "#FFF4E0" }}>
        <Txt variant="h3">Need help?</Txt>
        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>Reach out via support if anything looks wrong.</Txt>
        <Button testID="raise-dispute" title="Raise a dispute" variant="outline" style={{ marginTop: 12 }} onPress={() => router.push("/notifications")} />
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
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
