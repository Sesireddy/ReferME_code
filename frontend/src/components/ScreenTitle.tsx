import React from "react";
import { View, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "./Txt";
import { colors } from "@/src/theme/tokens";

type IconName = keyof typeof Ionicons.glyphMap;

export function ScreenTitle({
  title,
  icon,
  color,
  subtitle,
  right,
}: {
  title: string;
  icon: IconName;
  color?: string;
  subtitle?: string;
  right?: React.ReactNode;
}) {
  const c = color || colors.primary;
  return (
    <View style={styles.row}>
      <View style={styles.left}>
        <View style={[styles.iconBubble, { backgroundColor: hexToBg(c) }]}>
          <Ionicons name={icon} size={22} color={c} />
        </View>
        <View style={{ flex: 1, marginLeft: 10 }}>
          <Txt variant="h1" numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.75}>
            {title}
          </Txt>
          {subtitle ? (
            <Txt variant="muted" numberOfLines={3} style={{ marginTop: 2 }}>
              {subtitle}
            </Txt>
          ) : null}
        </View>
      </View>
      {right ? <View style={styles.right}>{right}</View> : null}
    </View>
  );
}

// Soft tinted background for the icon bubble (hex + alpha)
function hexToBg(hex: string): string {
  // Accept #RRGGBB → returns #RRGGBB1A (~10% opacity)
  if (/^#([0-9A-Fa-f]{6})$/.test(hex)) return `${hex}1F`;
  return "rgba(255,90,95,0.12)";
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  left: { flexDirection: "row", alignItems: "center", flex: 1 },
  iconBubble: { width: 44, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  right: { flexDirection: "row", alignItems: "center", gap: 8 },
});
