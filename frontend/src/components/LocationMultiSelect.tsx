import React, { useCallback, useMemo, useState } from "react";
import { View, StyleSheet, TouchableOpacity, TextInput, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius } from "@/src/theme/tokens";
import { Txt } from "@/src/components/Txt";
import { METRO_CITIES } from "@/src/lib/constants";

type Props = {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  label?: string;
  testID?: string;
  disabled?: boolean;
  /**
   * Additional cities the caller wants to include on top of `METRO_CITIES`
   * (useful for admin/employer flows). Deduplicated internally.
   */
  suggestions?: string[];
};

/**
 * LocationMultiSelect (Iter 66) — Search-as-you-type + chip-based multi-select
 * for Job Post "Location" field.
 *
 * Behaviour:
 * - Input filters the suggestion list; typing "B" surfaces Bangalore/Bhopal etc.
 * - Tapping a suggestion adds it as a chip and clears the input.
 * - Typing a custom city name + hitting "Add \"XYZ\"" pushes it as a chip too.
 * - Each chip has an ✕ to remove.
 * - Duplicate check is case-insensitive.
 */
export function LocationMultiSelect({
  value,
  onChange,
  placeholder = "Search Location…",
  label,
  testID,
  disabled,
  suggestions,
}: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const catalog = useMemo(() => {
    const merged = new Map<string, string>();
    for (const c of [...METRO_CITIES, ...(suggestions || [])]) {
      const k = c.trim().toLowerCase();
      if (!merged.has(k)) merged.set(k, c.trim());
    }
    return Array.from(merged.values()).sort((a, b) => a.localeCompare(b));
  }, [suggestions]);

  const selectedLower = useMemo(
    () => new Set(value.map((v) => v.trim().toLowerCase())),
    [value]
  );

  const listData = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = catalog.filter((c) => !selectedLower.has(c.toLowerCase()));
    if (!q) return filtered;
    const starts: string[] = [];
    const contains: string[] = [];
    for (const c of filtered) {
      const cl = c.toLowerCase();
      if (cl.startsWith(q)) starts.push(c);
      else if (cl.includes(q)) contains.push(c);
    }
    return [...starts, ...contains];
  }, [catalog, query, selectedLower]);

  const addCity = useCallback(
    (city: string) => {
      const clean = city.trim();
      if (!clean) return;
      const key = clean.toLowerCase();
      if (selectedLower.has(key)) return; // dedupe
      onChange([...value, clean]);
      setQuery("");
    },
    [onChange, value, selectedLower]
  );

  const removeCity = useCallback(
    (city: string) => {
      onChange(value.filter((v) => v.toLowerCase() !== city.toLowerCase()));
    },
    [onChange, value]
  );

  const showCustomAdd =
    query.trim().length >= 2 &&
    !listData.some((c) => c.toLowerCase() === query.trim().toLowerCase()) &&
    !selectedLower.has(query.trim().toLowerCase());

  return (
    <View style={{ marginBottom: 12 }}>
      {label ? <Txt variant="label" style={{ marginBottom: 6 }}>{label}</Txt> : null}

      {/* Chips */}
      {value.length > 0 ? (
        <View style={styles.chipsRow}>
          {value.map((c) => (
            <View key={c} style={styles.chip} testID={`loc-chip-${c}`}>
              <Ionicons name="location" size={13} color="#7C3AED" />
              <Txt style={styles.chipTxt} numberOfLines={1}>{c}</Txt>
              <TouchableOpacity
                onPress={() => removeCity(c)}
                hitSlop={8}
                testID={`loc-chip-remove-${c}`}
              >
                <Ionicons name="close-circle" size={16} color="#7C3AED" />
              </TouchableOpacity>
            </View>
          ))}
        </View>
      ) : null}

      {/* Search input */}
      <View style={[styles.inputWrap, disabled && { opacity: 0.6 }]}>
        <Ionicons name="search" size={16} color={colors.textSecondary} />
        <TextInput
          testID={testID || "loc-multiselect-input"}
          value={query}
          onChangeText={setQuery}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          placeholderTextColor={colors.textSecondary}
          style={styles.input}
          editable={!disabled}
          autoCorrect={false}
        />
        {query ? (
          <TouchableOpacity onPress={() => setQuery("")} hitSlop={10} testID="loc-clear">
            <Ionicons name="close-circle" size={18} color={colors.textSecondary} />
          </TouchableOpacity>
        ) : null}
      </View>

      {/* Dropdown */}
      {open && !disabled ? (
        <View style={styles.dropdown}>
          <ScrollView
            testID="loc-multiselect-list"
            style={styles.listScroll}
            nestedScrollEnabled
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator
          >
            {listData.length === 0 && !showCustomAdd ? (
              <View style={{ padding: 12 }}>
                <Txt variant="muted">No matches.</Txt>
              </View>
            ) : null}
            {listData.slice(0, 40).map((item) => (
              <TouchableOpacity
                key={item}
                onPress={() => addCity(item)}
                style={styles.row}
                testID={`loc-suggest-${item}`}
              >
                <Ionicons name="location-outline" size={14} color={colors.primary} />
                <Txt style={{ marginLeft: 8 }}>{item}</Txt>
              </TouchableOpacity>
            ))}
            {showCustomAdd ? (
              <TouchableOpacity
                onPress={() => addCity(query)}
                style={[styles.row, { backgroundColor: "#7C3AED0A" }]}
                testID="loc-add-custom"
              >
                <Ionicons name="add-circle" size={16} color="#7C3AED" />
                <Txt style={{ marginLeft: 8, color: "#7C3AED", fontWeight: "700" }}>
                  {`Add "${query.trim()}"`}
                </Txt>
              </TouchableOpacity>
            ) : null}
          </ScrollView>
          <View style={styles.dropdownFooter}>
            <TouchableOpacity onPress={() => setOpen(false)} testID="loc-close">
              <Txt variant="small" style={{ color: colors.primary, fontWeight: "700" }}>Done</Txt>
            </TouchableOpacity>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  chipsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
    marginBottom: 8,
  },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: "#7C3AED14",
    borderWidth: 1,
    borderColor: "#7C3AED40",
    maxWidth: "100%",
  },
  chipTxt: { color: "#7C3AED", fontWeight: "700", fontSize: 13 },
  inputWrap: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    height: 44,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    gap: 6,
  },
  input: { flex: 1, color: colors.textPrimary, fontSize: 15, paddingVertical: 0 },
  listScroll: { maxHeight: 220 },
  dropdown: {
    marginTop: 4,
    maxHeight: 260,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    overflow: "hidden",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  dropdownFooter: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    alignItems: "flex-end",
    backgroundColor: colors.surfaceAlt,
  },
});
