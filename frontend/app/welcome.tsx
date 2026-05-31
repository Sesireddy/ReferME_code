import React from "react";
import { View, StyleSheet, Image, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { SafeAreaView } from "react-native-safe-area-context";
import { Txt } from "@/src/components/Txt";
import { Button } from "@/src/components/Button";
import { colors } from "@/src/theme/tokens";

const HERO =
  "https://static.prod-images.emergentagent.com/jobs/d2f455eb-160b-40ff-9a4e-1d583c1869b0/images/a7d42b70a162d060c5cccdff45425f467967f3d394036f73402f239fdbbbe630.png";

export default function Welcome() {
  const router = useRouter();
  return (
    <LinearGradient colors={["#FFE8E9", "#FDFBF7", "#EFFFB8"]} style={styles.c}>
      <SafeAreaView edges={["top", "bottom"]} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ flexGrow: 1, padding: 24 }}>
          <View style={{ alignItems: "center", marginTop: 24 }}>
            <Image source={{ uri: HERO }} style={styles.hero} resizeMode="contain" />
          </View>
          <View style={{ marginTop: 24 }}>
            <Txt variant="label" style={{ color: colors.primary }}>Welcome to</Txt>
            <Txt variant="h1" style={{ fontSize: 44, color: colors.textPrimary }}>ReferME</Txt>
            <Txt variant="muted" style={{ marginTop: 12, fontSize: 16, lineHeight: 24 }}>
              Crack interviews, get referred, earn credits. The three-sided marketplace built for
              students, professionals & employers.
            </Txt>
          </View>
          <View style={{ flex: 1 }} />
          <View style={{ gap: 12, marginTop: 32 }}>
            <Button testID="welcome-signup-btn" title="Create account" onPress={() => router.push("/signup")} />
            <Button
              testID="welcome-login-btn"
              title="I already have an account"
              variant="outline"
              onPress={() => router.push("/login")}
            />
          </View>
        </ScrollView>
      </SafeAreaView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1 },
  hero: { width: 280, height: 280 },
});
