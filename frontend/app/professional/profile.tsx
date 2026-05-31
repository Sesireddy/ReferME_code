import React, { useEffect, useState, useCallback } from "react";
import { View, Alert, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors } from "@/src/theme/tokens";
import { api, clearSession } from "@/src/lib/api";

export default function ProProfile() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [designation, setDesignation] = useState("");
  const [years, setYears] = useState("");
  const [expertise, setExpertise] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const me = await api<{ user: any; profile: any }>("/auth/me");
      setUser(me.user);
      setName(me.user.name || "");
      setCompany(me.profile?.company || "");
      setDesignation(me.profile?.designation || "");
      setYears(String(me.profile?.experience_years ?? ""));
      setExpertise((me.profile?.expertise || []).join(", "));
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function save() {
    setBusy(true);
    try {
      await api("/profile", {
        method: "PUT",
        body: {
          name,
          company,
          designation,
          experience_years: parseInt(years || "0", 10),
          expertise: expertise.split(",").map((s) => s.trim()).filter(Boolean),
        },
      });
      Alert.alert("Saved", "Profile updated.");
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally { setBusy(false); }
  }

  async function logout() { await clearSession(); router.replace("/welcome"); }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <Txt variant="h1">Profile</Txt>
        <TouchableOpacity onPress={logout}><Ionicons name="log-out-outline" size={24} color={colors.textPrimary} /></TouchableOpacity>
      </View>
      <Card style={{ marginTop: 16 }}>
        <Txt variant="label">Email</Txt>
        <Txt variant="h3">{user?.email}</Txt>
      </Card>
      <View style={{ marginTop: 16 }}>
        <Input testID="pro-name" label="Full name" value={name} onChangeText={setName} />
        <Input testID="pro-company" label="Company" value={company} onChangeText={setCompany} />
        <Input testID="pro-designation" label="Designation" value={designation} onChangeText={setDesignation} />
        <Input testID="pro-years" label="Years of experience" value={years} onChangeText={setYears} keyboardType="number-pad" />
        <Input testID="pro-expertise" label="Expertise (comma-separated)" value={expertise} onChangeText={setExpertise} placeholder="System Design, React, ML" />
        <Button testID="pro-save" title="Save profile" loading={busy} onPress={save} />
      </View>
    </Screen>
  );
}
