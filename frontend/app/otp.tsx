import React, { useEffect, useRef, useState } from "react";
import { View, StyleSheet, TextInput, TouchableOpacity, Alert, KeyboardAvoidingView, Platform } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "@/src/components/Txt";
import { Button } from "@/src/components/Button";
import { colors, radius } from "@/src/theme/tokens";
import { api, setSession } from "@/src/lib/api";
import { routeByRole } from "./index";

export default function OtpScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ email: string; purpose?: "verify_email" | "reset_password"; hint?: string }>();
  const email = (params.email as string) || "";
  const purpose = (params.purpose as "verify_email" | "reset_password") || "verify_email";
  const hint = (params.hint as string) || "";
  const [digits, setDigits] = useState<string[]>(["", "", "", "", "", ""]);
  const refs = useRef<(TextInput | null)[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    refs.current[0]?.focus();
  }, []);

  function update(i: number, val: string) {
    const c = val.replace(/[^0-9]/g, "").slice(-1);
    const next = [...digits];
    next[i] = c;
    setDigits(next);
    if (c && i < 5) refs.current[i + 1]?.focus();
  }

  function handleKey(i: number, key: string) {
    if (key === "Backspace" && !digits[i] && i > 0) refs.current[i - 1]?.focus();
  }

  async function submit() {
    const otp = digits.join("");
    if (otp.length !== 6) return Alert.alert("Invalid OTP", "Enter all 6 digits.");
    setLoading(true);
    try {
      if (purpose === "verify_email") {
        const res = await api<{ token: string; user: any }>("/auth/verify-otp", {
          method: "POST",
          auth: false,
          body: { email, otp, purpose: "verify_email" },
        });
        await setSession(res.token, res.user);
        routeByRole(res.user.role, router);
      } else {
        // For reset: pass OTP to reset screen
        router.replace({ pathname: "/reset", params: { email, otp } });
      }
    } catch (e: any) {
      Alert.alert("OTP failed", e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.c} edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <View style={{ flex: 1, padding: 24 }}>
          <TouchableOpacity testID="back-btn" onPress={() => router.back()} hitSlop={10}>
            <Ionicons name="chevron-back" size={28} color={colors.textPrimary} />
          </TouchableOpacity>
          <Txt variant="h1" style={{ marginTop: 24 }}>Enter the code</Txt>
          <Txt variant="muted" style={{ marginTop: 6, marginBottom: 24 }}>
            We sent a 6-digit code to <Txt style={{ color: colors.textPrimary, fontWeight: "700" }}>{email}</Txt>
          </Txt>

          {hint ? (
            <View style={styles.hint}>
              <Ionicons name="information-circle" size={18} color={colors.warning} />
              <Txt variant="small" style={{ marginLeft: 8, flex: 1 }}>Mock OTP: <Txt style={{ fontWeight: "800" }}>{hint}</Txt></Txt>
            </View>
          ) : null}

          <View style={styles.row}>
            {digits.map((d, i) => (
              <TextInput
                key={i}
                testID={`otp-digit-${i}`}
                ref={(r) => { refs.current[i] = r; }}
                value={d}
                onChangeText={(v) => update(i, v)}
                onKeyPress={(e) => handleKey(i, e.nativeEvent.key)}
                keyboardType="number-pad"
                maxLength={1}
                style={styles.box}
              />
            ))}
          </View>

          <Button testID="otp-submit" title="Verify" onPress={submit} loading={loading} style={{ marginTop: 32 }} />
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.bg },
  row: { flexDirection: "row", justifyContent: "space-between", gap: 8 },
  box: {
    flex: 1,
    height: 64,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceAlt,
    textAlign: "center",
    fontSize: 28,
    fontWeight: "700",
    color: colors.textPrimary,
    borderWidth: 2,
    borderColor: colors.border,
  },
  hint: { flexDirection: "row", alignItems: "center", backgroundColor: "#FFF7E6", padding: 12, borderRadius: radius.md, marginBottom: 20 },
});
