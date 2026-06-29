import React, { useState } from "react";
import {
  TextInput,
  TextInputProps,
  View,
  StyleSheet,
  TouchableOpacity,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius } from "@/src/theme/tokens";
import { Txt } from "./Txt";

export function Input({
  label,
  error,
  secure,
  testID,
  ...props
}: TextInputProps & { label?: string; error?: string; secure?: boolean; testID?: string }) {
  const [focus, setFocus] = useState(false);
  const [hide, setHide] = useState(!!secure);
  // Read-only inputs should never adopt focus styling — they should look like
  // a flat pill identical to a disabled Picker so the saved profile reads as
  // a single premium read-only surface across all field types.
  const isReadOnly = props.editable === false;
  return (
    <View style={{ marginBottom: 14 }}>
      {label ? <Txt variant="label" style={{ marginBottom: 6 }}>{label}</Txt> : null}
      <View
        style={[
          styles.wrap,
          !isReadOnly && focus ? styles.focus : null,
          !isReadOnly && error ? styles.error : null,
          isReadOnly ? styles.readOnly : null,
        ]}
      >
        <TextInput
          testID={testID}
          placeholderTextColor={colors.textSecondary}
          {...props}
          secureTextEntry={hide}
          onFocus={(e) => {
            setFocus(true);
            props.onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocus(false);
            props.onBlur?.(e);
          }}
          style={[styles.input, props.style]}
        />
        {secure && !isReadOnly ? (
          <TouchableOpacity onPress={() => setHide((p) => !p)} hitSlop={10}>
            <Ionicons name={hide ? "eye-off" : "eye"} size={20} color={colors.textSecondary} />
          </TouchableOpacity>
        ) : null}
      </View>
      {error && !isReadOnly ? <Txt variant="small" style={{ color: colors.error, marginTop: 4 }}>{error}</Txt> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    paddingHorizontal: 14,
    paddingVertical: 4,
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 2,
    borderColor: "transparent",
  },
  focus: { borderColor: colors.primary, backgroundColor: colors.surface },
  error: { borderColor: colors.error },
  // Identical surface to Picker.boxDisabled — flat pill, no border, primary text.
  readOnly: {
    borderColor: "transparent",
    backgroundColor: colors.surfaceAlt,
  },
  input: {
    flex: 1,
    color: colors.textPrimary,
    fontSize: 16,
    paddingVertical: 12,
  },
});
