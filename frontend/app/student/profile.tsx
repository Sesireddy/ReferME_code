import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Alert, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors } from "@/src/theme/tokens";
import { api, clearSession } from "@/src/lib/api";

export default function StudentProfile() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [profile, setProfile] = useState<any>({});
  const [name, setName] = useState("");
  const [education, setEducation] = useState("");
  const [skills, setSkills] = useState("");
  const [resume, setResume] = useState("");
  const [score, setScore] = useState("");
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const me = await api<{ user: any; profile: any }>("/auth/me");
      setUser(me.user);
      setProfile(me.profile || {});
      setName(me.user.name || "");
      setEducation(me.profile?.education || "");
      setSkills((me.profile?.skills || []).join(", "));
      setResume(me.profile?.resume_base64 || "");
      setScore(String(me.profile?.resume_score || ""));
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function save() {
    setSaving(true);
    try {
      const res = await api<any>("/profile", {
        method: "PUT",
        body: {
          name,
          education,
          skills: skills.split(",").map((s) => s.trim()).filter(Boolean),
          resume_base64: resume || "uploaded-resume-placeholder",
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
        <Input testID="profile-resume" label="Resume (paste link or text)" value={resume} onChangeText={setResume} placeholder="https://... or text" multiline />
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

const styles = StyleSheet.create({});
