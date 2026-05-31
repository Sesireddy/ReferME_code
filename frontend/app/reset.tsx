import React, { useState } from "react";
import { View, ScrollView, TouchableOpacity, Alert, KeyboardAvoidingView, Platform, StyleSheet } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "@/src/components/Txt";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function Reset() {
  const router = useRouter();
  const params = useLocalSearchParams<{ email: string; otp: string }>();
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    if (password.length < 6) return Alert.alert("Weak password", "Use at least 6 characters.");
    setLoading(true);
    try {
      await api("/auth/reset-password", {
        method: "POST",
        auth: false,
        body: { email: params.email, otp: params.otp, new_password: password },
      });
      Alert.alert("Done", "Password reset. Please log in.");
      router.replace("/login");
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
          <Txt variant="h1" style={{ marginTop: 16 }}>Set new password</Txt>
          <Txt variant="muted" style={{ marginTop: 8, marginBottom: 24 }}>For {params.email}</Txt>
          <Input testID="reset-password" label="New password" placeholder="At least 6 chars" secure value={password} onChangeText={setPassword} />
          <Button testID="reset-submit" title="Reset password" onPress={submit} loading={loading} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
const styles = StyleSheet.create({ c: { flex: 1, backgroundColor: colors.bg } });
