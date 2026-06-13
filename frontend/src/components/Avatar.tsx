import React from "react";
import { View, Image, StyleSheet, TouchableOpacity } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Txt } from "./Txt";
import { colors } from "../theme/tokens";

interface AvatarProps {
  uri?: string | null;           // base64 data URL or remote URL
  name?: string | null;
  size?: number;                 // px
  onPress?: () => void;
  ring?: boolean;                // optional accent ring
  testID?: string;
}

/**
 * Avatar — displays a base64/URL image or a gradient-initials fallback.
 * Used in headers across student-facing screens (dashboard, jobs, interviews, leaderboard, profile, notifications).
 */
export function Avatar({ uri, name, size = 40, onPress, ring, testID }: AvatarProps) {
  const initial = (name || "?").trim().charAt(0).toUpperCase() || "?";
  const dim = { width: size, height: size, borderRadius: size / 2 };
  const ringStyle = ring ? styles.ring : null;
  const content = uri ? (
    <Image source={{ uri }} style={[dim, ringStyle]} resizeMode="cover" />
  ) : (
    <LinearGradient
      colors={["#FF5A5F", "#7C3AED"]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={[dim, styles.fallback, ringStyle]}
    >
      <Txt style={{ color: "#fff", fontSize: Math.round(size * 0.42), fontWeight: "800" }}>
        {initial}
      </Txt>
    </LinearGradient>
  );
  if (onPress) {
    return (
      <TouchableOpacity testID={testID} onPress={onPress} activeOpacity={0.8}>
        {content}
      </TouchableOpacity>
    );
  }
  return <View testID={testID}>{content}</View>;
}

const styles = StyleSheet.create({
  fallback: { alignItems: "center", justifyContent: "center" },
  ring: { borderWidth: 2, borderColor: colors.primary },
});
