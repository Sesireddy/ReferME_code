import React from "react";
import { Text, TextProps, StyleSheet } from "react-native";
import { colors } from "@/src/theme/tokens";

type Variant = "h1" | "h2" | "h3" | "body" | "small" | "label" | "muted";

export function Txt({ variant = "body", style, children, ...rest }: TextProps & { variant?: Variant }) {
  return (
    <Text {...rest} style={[styles.base, styles[variant], style]}>
      {children}
    </Text>
  );
}

const styles = StyleSheet.create({
  base: { color: colors.textPrimary },
  h1: { fontSize: 32, fontWeight: "800", letterSpacing: -0.5, lineHeight: 38 },
  h2: { fontSize: 24, fontWeight: "700", letterSpacing: -0.3 },
  h3: { fontSize: 18, fontWeight: "600" },
  body: { fontSize: 15, lineHeight: 22 },
  small: { fontSize: 13, lineHeight: 18 },
  label: { fontSize: 11, fontWeight: "700", letterSpacing: 1.5, textTransform: "uppercase", color: colors.textSecondary },
  muted: { fontSize: 14, color: colors.textSecondary },
});
