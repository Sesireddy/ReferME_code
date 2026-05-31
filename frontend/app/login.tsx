import React, { useState } from "react";
import { View, ScrollView, TouchableOpacity, Alert, KeyboardAvoidingView, Platform, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "@/src/components/Txt";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors } from "@/src/theme/tokens";
import { api, setSession } from "@/src/lib/api";
import { routeByRole } from "./index";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    if (!email || !password) return Alert.alert("Missing fields", "Enter email and password.");
    setLoading(true);
    try {
      const res = await api<{ token: string; user: any }>("/auth/login", {
        method: "POST",
        auth: false,
        body: { email: email.trim().toLowerCase(), password },
      });
      await setSession(res.token, res.user);
      routeByRole(res.user.role, router);
    } catch (e: any) {
      Alert.alert("Login failed", e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.c} edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
          <TouchableOpacity testID="back-btn" onPress={() => router.back()} hitSlop={10} style={{ marginBottom: 8 }}>
            <Ionicons name="chevron-back" size={28} color={colors.textPrimary} />
          </TouchableOpacity>
          <Txt variant="h1">Welcome back 👋</Txt>
          <Txt variant="muted" style={{ marginTop: 4, marginBottom: 28 }}>Log in to continue your journey</Txt>

          <Input testID="login-email" label="Email" placeholder="you@example.com" autoCapitalize="none" keyboardType="email-address" value={email} onChangeText={setEmail} />
          <Input testID="login-password" label="Password" placeholder="Your password" secure value={password} onChangeText={setPassword} />

          <TouchableOpacity onPress={() => router.push("/forgot")} style={{ alignSelf: "flex-end", marginBottom: 12 }}>
            <Txt style={{ color: colors.primary, fontWeight: "600" }}>Forgot password?</Txt>
          </TouchableOpacity>

          <Button testID="login-submit" title="Log in" onPress={handleLogin} loading={loading} />

          <View style={{ flexDirection: "row", alignItems: "center", marginVertical: 24 }}>
            <View style={{ flex: 1, height: 1, backgroundColor: colors.border }} />
            <Txt variant="small" style={{ marginHorizontal: 12, color: colors.textSecondary }}>or</Txt>
            <View style={{ flex: 1, height: 1, backgroundColor: colors.border }} />
          </View>

          <Button
            testID="google-login-btn"
            title="Continue with Google"
            variant="outline"
            icon={<Ionicons name="logo-google" size={18} color={colors.textPrimary} />}
            onPress={() => Alert.alert("Google login", "Available after deployment via Emergent Auth.")}
          />

          <TouchableOpacity onPress={() => router.replace("/signup")} style={{ alignSelf: "center", marginTop: 24 }}>
            <Txt variant="muted">New to ReferME? <Txt style={{ color: colors.primary, fontWeight: "700" }}>Sign up</Txt></Txt>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({ c: { flex: 1, backgroundColor: colors.bg } });
