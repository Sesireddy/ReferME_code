import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { View, StyleSheet, TouchableOpacity, TextInput, FlatList, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius } from "@/src/theme/tokens";
import { Txt } from "@/src/components/Txt";
import { api } from "@/src/lib/api";

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSelect?: (v: string) => void;
  placeholder?: string;
  label?: string;
  testID?: string;
  disabled?: boolean;
};

/**
 * SkillAutocomplete (Iteration 63) — searchable auto-complete for Skill fields.
 *
 * Backend contract: `GET /api/skills/suggest?q=<text>&limit=30` returns
 * `{ items: string[], total: number }`. Empty query → popular list.
 *
 * Behaviour per spec:
 *  - Placeholder: "Search or Select Skill"
 *  - Clicking the field displays popular skills.
 *  - Typing filters the list in real time (debounced 200ms).
 *  - Selecting a skill fills the field and closes the dropdown.
 *  - Case-insensitive starts-with matches ranked before contains-matches.
 */
export function SkillAutocomplete({ value, onChange, onSelect, placeholder = "Search or Select Skill", label, testID, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<any>(null);

  const fetchSuggestions = useCallback(async (q: string) => {
    setLoading(true);
    try {
      const r = await api<{ items: string[] }>(`/skills/suggest?q=${encodeURIComponent(q)}&limit=30`);
      setItems(r.items || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounced fetch on value change while the dropdown is open.
  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(value), 200);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [value, open, fetchSuggestions]);

  const handleFocus = useCallback(() => {
    if (disabled) return;
    setOpen(true);
    // Load popular skills immediately on focus.
    if (items.length === 0) fetchSuggestions("");
  }, [disabled, items.length, fetchSuggestions]);

  const handleSelect = useCallback((s: string) => {
    onChange(s);
    setOpen(false);
    onSelect?.(s);
  }, [onChange, onSelect]);

  const listData = useMemo(() => items.slice(0, 30), [items]);

  return (
    <View style={{ marginBottom: 12 }}>
      {label ? <Txt variant="label" style={{ marginBottom: 6 }}>{label}</Txt> : null}
      <View style={[styles.inputWrap, disabled && { opacity: 0.6 }]}>
        <Ionicons name="search" size={16} color={colors.textSecondary} />
        <TextInput
          testID={testID || "skill-autocomplete-input"}
          value={value}
          onChangeText={onChange}
          onFocus={handleFocus}
          placeholder={placeholder}
          placeholderTextColor={colors.textSecondary}
          style={styles.input}
          editable={!disabled}
          autoCorrect={false}
          autoCapitalize="none"
        />
        {value ? (
          <TouchableOpacity onPress={() => onChange("")} hitSlop={10} testID="skill-clear">
            <Ionicons name="close-circle" size={18} color={colors.textSecondary} />
          </TouchableOpacity>
        ) : null}
      </View>

      {open && !disabled ? (
        <View style={styles.dropdown}>
          {loading ? (
            <View style={{ padding: 12, alignItems: "center" }}>
              <ActivityIndicator size="small" color={colors.primary} />
            </View>
          ) : listData.length === 0 ? (
            <View style={{ padding: 12 }}>
              <Txt variant="muted">No matches. Press Enter to use "{value}"</Txt>
              {value ? (
                <TouchableOpacity onPress={() => handleSelect(value)} style={{ paddingVertical: 8 }} testID="skill-use-custom">
                  <Txt style={{ color: colors.primary, fontWeight: "700" }}>Use "{value}"</Txt>
                </TouchableOpacity>
              ) : null}
            </View>
          ) : (
            <FlatList
              testID="skill-autocomplete-list"
              data={listData}
              keyExtractor={(s) => s}
              keyboardShouldPersistTaps="handled"
              renderItem={({ item }) => (
                <TouchableOpacity
                  onPress={() => handleSelect(item)}
                  style={styles.row}
                  testID={`skill-suggest-${item}`}
                >
                  <Ionicons name="pricetag" size={14} color={colors.primary} />
                  <Txt style={{ marginLeft: 8 }}>{item}</Txt>
                </TouchableOpacity>
              )}
            />
          )}
          <View style={styles.dropdownFooter}>
            <TouchableOpacity onPress={() => setOpen(false)} testID="skill-close">
              <Txt variant="small" style={{ color: colors.primary, fontWeight: "700" }}>Close</Txt>
            </TouchableOpacity>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
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
