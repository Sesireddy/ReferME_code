import React, { useState } from "react";
import { TouchableOpacity, View, StyleSheet, Modal, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius } from "@/src/theme/tokens";
import { Txt } from "./Txt";

export function Picker<T extends string | number>({
  label,
  options,
  value,
  onChange,
  placeholder = "Select",
  testID,
  disabled = false,
}: {
  label?: string;
  options: { value: T; label: string }[];
  value: T | null | undefined;
  onChange: (v: T) => void;
  placeholder?: string;
  testID?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.value === value);
  return (
    <View style={{ marginBottom: 14 }}>
      {label ? <Txt variant="label" style={{ marginBottom: 6 }}>{label}</Txt> : null}
      <TouchableOpacity
        testID={testID}
        activeOpacity={disabled ? 1 : 0.85}
        disabled={disabled}
        onPress={() => !disabled && setOpen(true)}
        style={[styles.box, disabled ? styles.boxDisabled : null]}
      >
        <Txt style={{ flex: 1, color: current ? colors.textPrimary : colors.textSecondary, fontSize: 16 }}>
          {current ? current.label : placeholder}
        </Txt>
        {!disabled ? <Ionicons name="chevron-down" size={20} color={colors.textSecondary} /> : null}
      </TouchableOpacity>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <TouchableOpacity activeOpacity={1} style={styles.bg} onPress={() => setOpen(false)}>
          <View style={styles.sheet}>
            <Txt variant="h3" style={{ marginBottom: 8 }}>{label || "Select"}</Txt>
            <ScrollView>
              {options.map((o) => {
                const active = o.value === value;
                return (
                  <TouchableOpacity
                    key={String(o.value)}
                    testID={`${testID}-opt-${o.value}`}
                    onPress={() => { onChange(o.value); setOpen(false); }}
                    style={[styles.row, active ? styles.rowActive : null]}
                  >
                    <Txt style={{ flex: 1, fontWeight: active ? "700" : "500" }}>{o.label}</Txt>
                    {active ? <Ionicons name="checkmark" size={18} color={colors.primary} /> : null}
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </View>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    paddingHorizontal: 14,
    paddingVertical: 14,
    borderWidth: 2,
    borderColor: "transparent",
  },
  boxDisabled: { opacity: 0.55 },
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.bg, padding: 20, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: "70%" },
  row: { paddingVertical: 14, flexDirection: "row", alignItems: "center", borderBottomWidth: 1, borderBottomColor: colors.border },
  rowActive: { backgroundColor: "#FFF5F5" },
});
