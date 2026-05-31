import React from "react";
import { TouchableOpacity, StyleSheet, ActivityIndicator, View, ViewStyle } from "react-native";
import { colors, radius, shadow } from "@/src/theme/tokens";
import { Txt } from "./Txt";

type Variant = "primary" | "secondary" | "outline" | "ghost" | "danger";

export function Button({
  title,
  onPress,
  variant = "primary",
  loading,
  disabled,
  style,
  testID,
  icon,
}: {
  title: string;
  onPress?: () => void;
  variant?: Variant;
  loading?: boolean;
  disabled?: boolean;
  style?: ViewStyle;
  testID?: string;
  icon?: React.ReactNode;
}) {
  const isDisabled = disabled || loading;
  return (
    <TouchableOpacity
      testID={testID}
      activeOpacity={0.85}
      disabled={isDisabled}
      onPress={onPress}
      style={[
        styles.base,
        variants[variant],
        isDisabled ? styles.disabled : null,
        variant === "primary" ? shadow.glow : null,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={variant === "secondary" ? colors.textPrimary : "#fff"} />
      ) : (
        <View style={styles.row}>
          {icon}
          <Txt
            style={{
              color:
                variant === "secondary"
                  ? colors.textPrimary
                  : variant === "outline" || variant === "ghost"
                    ? colors.textPrimary
                    : "#fff",
              fontWeight: "700",
              fontSize: 16,
            }}
          >
            {title}
          </Txt>
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  base: {
    height: 52,
    borderRadius: radius.full,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 20,
  },
  row: { flexDirection: "row", alignItems: "center", gap: 8 },
  disabled: { opacity: 0.5 },
});

const variants: Record<Variant, ViewStyle> = {
  primary: { backgroundColor: colors.primary },
  secondary: { backgroundColor: colors.secondary },
  outline: { backgroundColor: "transparent", borderWidth: 2, borderColor: colors.border },
  ghost: { backgroundColor: "transparent" },
  danger: { backgroundColor: colors.error },
};
