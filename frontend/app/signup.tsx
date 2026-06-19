import React, { useState } from "react";
import { View, StyleSheet, ScrollView, TouchableOpacity, Alert, KeyboardAvoidingView, Platform, TextInput, ActivityIndicator } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "@/src/components/Txt";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { Card } from "@/src/components/Card";
import { colors, radius } from "@/src/theme/tokens";
import { api, setSession } from "@/src/lib/api";
import { ConfirmDialog } from "@/src/components/ConfirmDialog";
import * as Linking from "expo-linking";

type Role = "student" | "professional" | "employer";

const ROLES: { id: Role; title: string; subtitle: string; icon: any; color: string }[] = [
  { id: "student", title: "I'm a Job Seeker", subtitle: "Book Mock Interviews & Get Referred", icon: "school", color: colors.primary },
  { id: "professional", title: "I'm a Professional", subtitle: "Conduct Interviews, Refer Candidates & Earn Credits", icon: "briefcase", color: "#7C3AED" },
  { id: "employer", title: "I'm an Employer", subtitle: "Post jobs & hire great talent", icon: "business", color: "#2563EB" },
];

export default function Signup() {
  const router = useRouter();
  const params = useLocalSearchParams<{ ref?: string }>();
  const [role, setRole] = useState<Role | null>("student");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // Referral code: prefilled from URL ?ref=, user can edit/clear.
  const [refCode, setRefCode] = useState<string>(((params.ref as string) || "").toString().trim().toUpperCase());
  const [refStatus, setRefStatus] = useState<"idle" | "checking" | "valid" | "invalid">("idle");
  const [refMessage, setRefMessage] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [employerDialog, setEmployerDialog] = useState(false);

  // Debounced live validation of the referral code
  React.useEffect(() => {
    const code = (refCode || "").trim().toUpperCase();
    if (!code) {
      setRefStatus("idle");
      setRefMessage("");
      return;
    }
    setRefStatus("checking");
    setRefMessage("");
    const t = setTimeout(async () => {
      try {
        const r = await api<{ valid: boolean; message?: string; owner_name?: string }>(
          `/refer/validate?code=${encodeURIComponent(code)}`,
          { auth: false }
        );
        if (r.valid) {
          setRefStatus("valid");
          setRefMessage(r.owner_name ? `Referred by ${r.owner_name}` : "Valid code ✓");
        } else {
          setRefStatus("invalid");
          setRefMessage(r.message || "Invalid referral code. Please check and try again.");
        }
      } catch {
        setRefStatus("invalid");
        setRefMessage("Could not validate. Please try again.");
      }
    }, 450);
    return () => clearTimeout(t);
  }, [refCode]);

  function selectRole(r: Role) {
    if (r === "employer") {
      setEmployerDialog(true);
      return;
    }
    setRole(r);
  }

  async function handleSignup() {
    if (!role) return Alert.alert("Pick a role", "Choose Student, Professional, or Employer.");
    if (!email || !password) return Alert.alert("Missing fields", "Enter email and password.");
    if (password.length < 6) return Alert.alert("Weak password", "Use at least 6 characters.");
    if (refCode && refStatus === "invalid") {
      return Alert.alert(
        "Invalid referral code",
        "Please correct the referral code or clear the field to continue."
      );
    }
    setLoading(true);
    try {
      const res = await api<{ email: string; mock_otp?: string }>("/auth/signup", {
        method: "POST",
        auth: false,
        body: { email: email.trim().toLowerCase(), password, role, name, ref: refCode || undefined },
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
          <Txt variant="muted" style={{ marginTop: 4, marginBottom: 20 }}>Pick how you&apos;ll use ReferME</Txt>

          <View style={{ gap: 12, marginBottom: 20 }}>
            {ROLES.map((r) => {
              const active = role === r.id;
              return (
                <TouchableOpacity
                  key={r.id}
                  testID={`role-${r.id}`}
                  onPress={() => selectRole(r.id)}
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

          {/* Referral Code (Optional) */}
          <View style={{ marginTop: 4 }}>
            <Txt variant="label" style={{ marginBottom: 6, color: colors.textSecondary }}>
              Referral Code (Optional)
            </Txt>
            <View
              style={[
                styles.refField,
                refStatus === "invalid" && { borderColor: colors.error },
                refStatus === "valid" && { borderColor: colors.success },
              ]}
            >
              <Ionicons name="gift-outline" size={18} color={colors.textSecondary} />
              <TextInput
                testID="signup-ref"
                value={refCode}
                onChangeText={(t) => setRefCode(t.toUpperCase().replace(/\s+/g, ""))}
                placeholder="Enter Referral Code (Optional)"
                placeholderTextColor={colors.textSecondary}
                autoCapitalize="characters"
                autoCorrect={false}
                style={styles.refInput}
              />
              {refStatus === "checking" ? (
                <ActivityIndicator size="small" color={colors.primary} />
              ) : refStatus === "valid" ? (
                <Ionicons name="checkmark-circle" size={20} color={colors.success} />
              ) : refStatus === "invalid" ? (
                <Ionicons name="alert-circle" size={20} color={colors.error} />
              ) : refCode ? (
                <TouchableOpacity onPress={() => setRefCode("")} hitSlop={8}>
                  <Ionicons name="close-circle" size={18} color={colors.textSecondary} />
                </TouchableOpacity>
              ) : null}
            </View>
            {refMessage ? (
              <Txt
                testID="signup-ref-msg"
                variant="small"
                style={{
                  color: refStatus === "valid" ? colors.success : refStatus === "invalid" ? colors.error : colors.textSecondary,
                  marginTop: 6,
                  marginLeft: 4,
                }}
              >
                {refMessage}
              </Txt>
            ) : null}
          </View>

          <Button
            testID="signup-submit"
            title="Send OTP"
            onPress={handleSignup}
            loading={loading}
            disabled={refCode.length > 0 && refStatus === "invalid"}
            style={{ marginTop: 16 }}
          />
          <TouchableOpacity onPress={() => router.replace("/login")} style={{ alignSelf: "center", marginTop: 18 }}>
            <Txt variant="muted">Already have an account? <Txt style={{ color: colors.primary, fontWeight: "700" }}>Log in</Txt></Txt>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>

      <ConfirmDialog
        visible={employerDialog}
        title="Employer access"
        message="For employer assistance, please contact our team at Team@referme.today"
        confirmLabel="Contact Team"
        cancelLabel="Close"
        onCancel={() => setEmployerDialog(false)}
        onConfirm={() => {
          setEmployerDialog(false);
          Linking.openURL("mailto:Team@referme.today?subject=Employer%20Onboarding%20-%20ReferME");
        }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.bg },
  roleIcon: { width: 56, height: 56, borderRadius: radius.lg, alignItems: "center", justifyContent: "center" },
  refField: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    paddingHorizontal: 12,
    height: 48,
    gap: 8,
  },
  refInput: { flex: 1, color: colors.textPrimary, fontSize: 14, paddingVertical: 0, letterSpacing: 1 },
});
