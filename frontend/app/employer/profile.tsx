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
import { ScreenTitle } from "@/src/components/ScreenTitle";

export default function EmpProfile() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [website, setWebsite] = useState("");
  const [size, setSize] = useState("");
  const [bio, setBio] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const me = await api<{ user: any; profile: any }>("/auth/me");
      setUser(me.user);
      setName(me.user.name || "");
      setCompany(me.profile?.company_name || "");
      setWebsite(me.profile?.company_website || "");
      setSize(me.profile?.company_size || "");
      setBio(me.profile?.bio || "");
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function save() {
    setBusy(true);
    try {
      await api("/profile", {
        method: "PUT",
        body: { name, company_name: company, company_website: website, company_size: size, bio },
      });
      Alert.alert("Saved");
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally { setBusy(false); }
  }

  async function logout() { await clearSession(); router.replace("/welcome"); }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <View style={{ flex: 1 }}>
          <ScreenTitle title="Profile" icon="person-circle" color="#2563EB" />
        </View>
        <TouchableOpacity testID="emp-logout" onPress={logout} hitSlop={10}>
          <Ionicons name="log-out-outline" size={24} color={colors.textPrimary} />
        </TouchableOpacity>
      </View>
      <Card style={{ marginTop: 16 }}>
        <Txt variant="label">Email</Txt>
        <Txt variant="h3">{user?.email}</Txt>
      </Card>
      <View style={{ marginTop: 16 }}>
        <Input testID="emp-name" label="Your name" value={name} onChangeText={setName} />
        <Input testID="emp-company" label="Company name" value={company} onChangeText={setCompany} />
        <Input testID="emp-website" label="Company website" value={website} onChangeText={setWebsite} placeholder="company.com" />
        <Input testID="emp-size" label="Company size" value={size} onChangeText={setSize} placeholder="50-200" />
        <Input testID="emp-bio" label="About" value={bio} onChangeText={setBio} multiline />
        <Button testID="emp-save" title="Save profile" loading={busy} onPress={save} />
      </View>
      <Card style={{ marginTop: 16, backgroundColor: "#EAF3FF" }}>
        <Txt variant="h3">Need help?</Txt>
        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>Email support@referme.app for dedicated assistance.</Txt>
      </Card>
    </Screen>
  );
}
