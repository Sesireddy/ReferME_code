import React from "react";
import { View, ViewStyle } from "react-native";
import { colors, radius, shadow } from "@/src/theme/tokens";

export function Card({
  children,
  style,
  highlight,
  padding = 16,
}: {
  children: React.ReactNode;
  style?: ViewStyle;
  highlight?: boolean;
  padding?: number;
}) {
  return (
    <View
      style={[
        {
          backgroundColor: colors.surface,
          borderRadius: radius.xl,
          padding,
          borderWidth: highlight ? 2 : 1,
          borderColor: highlight ? colors.secondary : colors.border,
        },
        shadow.card,
        style,
      ]}
    >
      {children}
    </View>
  );
}
