import React, { useState } from "react";
import { View, StyleSheet, ScrollView, TouchableOpacity, Alert, KeyboardAvoidingView, Platform } from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "@/src/components/Txt";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { Card } from "@/src/components/Card";
import { colors, radius } from "@/src/theme/tokens";
import { api, setSession } from "@/src/lib/api";

type Role = "student" | "professional" | "employer";

const ROLES: { id: Role; title: string; subtitle: string; icon: any; color: string }[] = [
  { id: "student", title: "I'm a Student", subtitle: "Get referred & book mock interviews", icon: "school", color: colors.primary },
  { id: "professional", title: "I'm a Professional", subtitle: "Conduct interviews & earn credits", icon: "briefcase", color: "#7C3AED" },
  { id: "employer", title: "I'm an Employer", subtitle: "Post jobs & hire great talent", icon: "business", color: "#2563EB" },
];

export default function Signup() {
  const router = useRouter();
  const [role, setRole] = useState<Role | null>("student");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSignup() {
    if (!role) return Alert.alert("Pick a role", "Choose Student, Professional, or Employer.");
    if (!email || !password) return Alert.alert("Missing fields", "Enter email and password.");
    if (password.length < 6) return Alert.alert("Weak password", "Use at least 6 characters.");
    setLoading(true);
    try {
      const res = await api<{ email: string; mock_otp?: string }>("/auth/signup", {
        method: "POST",
        auth: false,
        body: { email: email.trim().toLowerCase(), password, role, name },
      });
      router.push({ pathname: "/otp", params: { email: res.email, purpose: "verify_email", hint: res.mock_otp || "" } });
    } catch (e: any) {
      Alert.alert("Signup failed", e.message);
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
          <Txt variant="h1">Create account</Txt>
          <Txt variant="muted" style={{ marginTop: 4, marginBottom: 20 }}>Pick how you'll use ReferME</Txt>

          <View style={{ gap: 12, marginBottom: 20 }}>
            {ROLES.map((r) => {
              const active = role === r.id;
              return (
                <TouchableOpacity
                  key={r.id}
                  testID={`role-${r.id}`}
                  onPress={() => setRole(r.id)}
                  activeOpacity={0.85}
                >
                  <Card highlight={active} style={{ borderColor: active ? r.color : colors.border, borderWidth: 2 }}>
                    <View style={{ flexDirection: "row", alignItems: "center" }}>
                      <View style={[styles.roleIcon, { backgroundColor: r.color + "20" }]}>
                        <Ionicons name={r.icon} size={28} color={r.color} />
                      </View>
                      <View style={{ flex: 1, marginLeft: 14 }}>
                        <Txt variant="h3">{r.title}</Txt>
                        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>{r.subtitle}</Txt>
                      </View>
                      {active ? <Ionicons name="checkmark-circle" size={24} color={r.color} /> : null}
                    </View>
                  </Card>
                </TouchableOpacity>
              );
            })}
          </View>

          <Input testID="signup-name" label="Full name (optional)" placeholder="Jane Doe" value={name} onChangeText={setName} autoCapitalize="words" />
          <Input testID="signup-email" label="Email" placeholder="you@example.com" autoCapitalize="none" keyboardType="email-address" value={email} onChangeText={setEmail} />
          <Input testID="signup-password" label="Password" placeholder="At least 6 characters" secure value={password} onChangeText={setPassword} />

          <Button testID="signup-submit" title="Send OTP" onPress={handleSignup} loading={loading} style={{ marginTop: 8 }} />
          <TouchableOpacity onPress={() => router.replace("/login")} style={{ alignSelf: "center", marginTop: 18 }}>
            <Txt variant="muted">Already have an account? <Txt style={{ color: colors.primary, fontWeight: "700" }}>Log in</Txt></Txt>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.bg },
  roleIcon: { width: 56, height: 56, borderRadius: radius.lg, alignItems: "center", justifyContent: "center" },
});
