import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { View, StyleSheet, TouchableOpacity, TextInput, ScrollView, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius } from "@/src/theme/tokens";
import { Txt } from "@/src/components/Txt";
import { api } from "@/src/lib/api";

type Props = {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  label?: string;
  testID?: string;
  disabled?: boolean;
};

/**
 * SkillMultiSelect (Iter 71) — searchable, chip-based multi-select for
 * technical skills. Backed by `GET /api/skills/suggest?q=<text>` which
 * aggregates from Admin Master Skills + existing job seeker / pro profiles
 * + job postings + mock interview skill sets (dedup already handled server-
 * side).
 *
 * Behaviour:
 *  - Focus shows popular skills.
 *  - Type-ahead filters in real-time (200ms debounce).
 *  - Tap a suggestion → chip added, input cleared, dropdown stays open for
 *    another selection.
 *  - Custom "Add \"XYZ\"" row appears if user types something not in the
 *    catalog.
 *  - Selected chips render with an ✕ to remove; duplicate check is case-
 *    insensitive.
 */
export function SkillMultiSelect({
  value,
  onChange,
  placeholder = "Type to search skills…",
  label,
  testID,
  disabled,
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<any>(null);

  const selectedLower = useMemo(
    () => new Set(value.map((v) => v.trim().toLowerCase())),
    [value],
  );

  const fetchSuggestions = useCallback(async (q: string) => {
    setLoading(true);
    try {
      const r = await api<{ items: string[] }>(`/skills/suggest?q=${encodeURIComponent(q)}&limit=40`);
      setItems(r.items || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(query), 200);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, open, fetchSuggestions]);

  const handleFocus = useCallback(() => {
    if (disabled) return;
    setOpen(true);
    if (items.length === 0) fetchSuggestions("");
  }, [disabled, items.length, fetchSuggestions]);

  const addSkill = useCallback(
    (s: string) => {
      const clean = s.trim();
      if (!clean) return;
      if (selectedLower.has(clean.toLowerCase())) return;
      onChange([...value, clean]);
      setQuery("");
    },
    [onChange, value, selectedLower],
  );

  const removeSkill = useCallback(
    (s: string) => {
      onChange(value.filter((v) => v.toLowerCase() !== s.toLowerCase()));
    },
    [onChange, value],
  );

  const listData = useMemo(
    () => items.filter((s) => !selectedLower.has(s.toLowerCase())).slice(0, 40),
    [items, selectedLower],
  );

  const showCustomAdd =
    query.trim().length >= 2 &&
    !listData.some((s) => s.toLowerCase() === query.trim().toLowerCase()) &&
    !selectedLower.has(query.trim().toLowerCase());

  return (
    <View style={{ marginBottom: 12 }}>
      {label ? <Txt variant="label" style={{ marginBottom: 6 }}>{label}</Txt> : null}

      {/* Selected chips */}
      {value.length > 0 ? (
        <View style={styles.chipsRow}>
          {value.map((s) => (
            <View key={s} style={styles.chip} testID={`skill-chip-${s}`}>
              <Ionicons name="pricetag" size={12} color="#7C3AED" />
              <Txt style={styles.chipTxt} numberOfLines={1}>{s}</Txt>
              <TouchableOpacity onPress={() => removeSkill(s)} hitSlop={8} testID={`skill-chip-remove-${s}`}>
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
          testID={testID || "skill-multiselect-input"}
          value={query}
          onChangeText={setQuery}
          onFocus={handleFocus}
          placeholder={placeholder}
          placeholderTextColor={colors.textSecondary}
          style={styles.input}
          editable={!disabled}
          autoCorrect={false}
          autoCapitalize="none"
        />
        {query ? (
          <TouchableOpacity onPress={() => setQuery("")} hitSlop={10}>
            <Ionicons name="close-circle" size={18} color={colors.textSecondary} />
          </TouchableOpacity>
        ) : null}
      </View>

      {/* Dropdown */}
      {open && !disabled ? (
        <View style={styles.dropdown}>
          {loading ? (
            <View style={{ padding: 12, alignItems: "center" }}>
              <ActivityIndicator size="small" color={colors.primary} />
            </View>
          ) : (
            <ScrollView
              testID="skill-multiselect-list"
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
              {listData.map((item) => (
                <TouchableOpacity
                  key={item}
                  onPress={() => addSkill(item)}
                  style={styles.row}
                  testID={`skill-suggest-${item}`}
                >
                  <Ionicons name="pricetag-outline" size={14} color={colors.primary} />
                  <Txt style={{ marginLeft: 8 }}>{item}</Txt>
                </TouchableOpacity>
              ))}
              {showCustomAdd ? (
                <TouchableOpacity
                  onPress={() => addSkill(query)}
                  style={[styles.row, { backgroundColor: "#7C3AED0A" }]}
                  testID="skill-add-custom"
                >
                  <Ionicons name="add-circle" size={16} color="#7C3AED" />
                  <Txt style={{ marginLeft: 8, color: "#7C3AED", fontWeight: "700" }}>
                    {`Add "${query.trim()}"`}
                  </Txt>
                </TouchableOpacity>
              ) : null}
            </ScrollView>
          )}
          <View style={styles.dropdownFooter}>
            <TouchableOpacity onPress={() => setOpen(false)} testID="skill-close">
              <Txt variant="small" style={{ color: colors.primary, fontWeight: "700" }}>Done</Txt>
            </TouchableOpacity>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginBottom: 8 },
  chip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: "#7C3AED14",
    borderWidth: 1, borderColor: "#7C3AED40",
    maxWidth: "100%",
  },
  chipTxt: { color: "#7C3AED", fontWeight: "700", fontSize: 13 },
  inputWrap: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 10, height: 44,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surface, gap: 6,
  },
  input: { flex: 1, color: colors.textPrimary, fontSize: 15, paddingVertical: 0 },
  listScroll: { maxHeight: 220 },
  dropdown: {
    marginTop: 4, maxHeight: 260,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    backgroundColor: colors.surface, overflow: "hidden",
  },
  row: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 12, paddingVertical: 10,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  dropdownFooter: {
    paddingHorizontal: 12, paddingVertical: 8,
    alignItems: "flex-end", backgroundColor: colors.surfaceAlt,
  },
});
