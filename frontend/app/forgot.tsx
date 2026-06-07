import React, { useState } from "react";
import { View, ScrollView, TouchableOpacity, Alert, KeyboardAvoidingView, Platform, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "@/src/components/Txt";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function Forgot() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);

  async function send() {
    if (!email) return Alert.alert("Missing email");
    setLoading(true);
    try {
      const res = await api<{ mock_otp?: string }>("/auth/forgot-password", {
        method: "POST",
        auth: false,
        body: { email: email.trim().toLowerCase() },
      });
      router.push({ pathname: "/otp", params: { email: email.trim().toLowerCase(), purpose: "reset_password", hint: res.mock_otp || "" } });
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.c} edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: 24 }} keyboardShouldPersistTaps="handled">
          <TouchableOpacity onPress={() => router.back()} hitSlop={10}>
            <Ionicons name="chevron-back" size={28} color={colors.textPrimary} />
          </TouchableOpacity>
          <Txt variant="h1" style={{ marginTop: 16 }}>Forgot password?</Txt>
          <Txt variant="muted" style={{ marginTop: 8, marginBottom: 24 }}>We&apos;ll send a 6-digit OTP to reset your password.</Txt>
          <Input testID="forgot-email" label="Email" placeholder="you@example.com" autoCapitalize="none" keyboardType="email-address" value={email} onChangeText={setEmail} />
          <Button testID="forgot-submit" title="Send reset code" onPress={send} loading={loading} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
const styles = StyleSheet.create({ c: { flex: 1, backgroundColor: colors.bg } });
