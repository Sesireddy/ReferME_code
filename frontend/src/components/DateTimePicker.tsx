import React, { useMemo, useState, useEffect } from "react";
import { View, StyleSheet, Modal, TouchableOpacity, FlatList, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "@/src/components/Txt";
import { Button } from "@/src/components/Button";
import { colors, radius } from "@/src/theme/tokens";

/**
 * Cross-platform date picker — opens a custom modal with a vertical
 * list of selectable days. Manual text entry is disabled (per product spec).
 *
 * value/onChange: ISO `YYYY-MM-DD` string.
 * minDate / maxDate: optional Date bounds.
 */
export function DatePickerField({
  label,
  value,
  onChange,
  minDate,
  maxDate,
  placeholder = "Select date",
  testID,
}: {
  label?: string;
  value?: string;
  onChange: (iso: string) => void;
  minDate?: Date;
  maxDate?: Date;
  placeholder?: string;
  testID?: string;
}) {
  const [open, setOpen] = useState(false);

  const today = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }, []);

  const dates = useMemo(() => {
    const start = minDate ? new Date(minDate) : today;
    start.setHours(0, 0, 0, 0);
    const end = maxDate ? new Date(maxDate) : new Date(start.getTime() + 90 * 86400000);
    const out: Date[] = [];
    const cursor = new Date(start);
    while (cursor <= end) {
      out.push(new Date(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    return out;
  }, [minDate, maxDate, today]);

  function fmt(d: Date): string {
    return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  }
  function iso(d: Date): string {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${dd}`;
  }

  const display = value ? fmt(new Date(value + "T00:00:00")) : placeholder;

  return (
    <View style={{ marginBottom: 12 }}>
      {label ? <Txt variant="label" style={styles.label}>{label}</Txt> : null}
      <TouchableOpacity testID={testID || "date-picker-trigger"} style={styles.trigger} onPress={() => setOpen(true)} activeOpacity={0.8}>
        <Ionicons name="calendar" size={20} color={colors.textSecondary} />
        <Txt style={{ marginLeft: 10, color: value ? colors.textPrimary : colors.textSecondary, flex: 1 }}>
          {display}
        </Txt>
        <Ionicons name="chevron-down" size={18} color={colors.textSecondary} />
      </TouchableOpacity>

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <View style={styles.modalBg}>
          <View style={styles.sheet}>
            <View style={styles.sheetHeader}>
              <Txt variant="h2">{label || "Select date"}</Txt>
              <TouchableOpacity onPress={() => setOpen(false)}>
                <Ionicons name="close" size={26} color={colors.textPrimary} />
              </TouchableOpacity>
            </View>
            <FlatList
              data={dates}
              keyExtractor={(d) => iso(d)}
              initialNumToRender={20}
              renderItem={({ item }) => {
                const sel = value === iso(item);
                return (
                  <TouchableOpacity
                    testID={`date-${iso(item)}`}
                    style={[styles.row, sel && styles.rowSelected]}
                    onPress={() => { onChange(iso(item)); setOpen(false); }}
                  >
                    <Txt style={{ fontWeight: sel ? "700" : "500", color: sel ? "#fff" : colors.textPrimary }}>
                      {fmt(item)}
                    </Txt>
                    {sel ? <Ionicons name="checkmark" size={20} color="#fff" /> : null}
                  </TouchableOpacity>
                );
              }}
              style={{ maxHeight: 380 }}
            />
            <Button title="Close" variant="secondary" onPress={() => setOpen(false)} style={{ marginTop: 8 }} />
          </View>
        </View>
      </Modal>
    </View>
  );
}

/**
 * 12-hour AM/PM time picker. Value/onChange in HH:MM (24h) for backend consistency,
 * but the UI presents 12-hour with AM/PM as required by spec.
 */
export function TimePickerField({
  label,
  value,
  onChange,
  minuteStep = 15,
  testID,
  placeholder = "Select time",
}: {
  label?: string;
  value?: string;  // "HH:MM" 24h
  onChange: (hm24: string) => void;
  minuteStep?: number;
  testID?: string;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [period, setPeriod] = useState<"AM" | "PM">(() => {
    if (!value) return "AM";
    const h = parseInt(value.split(":")[0] || "0", 10);
    return h >= 12 ? "PM" : "AM";
  });
  const [hour12, setHour12] = useState<number>(() => {
    if (!value) return 9;
    const h = parseInt(value.split(":")[0] || "0", 10);
    const h12 = h % 12 || 12;
    return h12;
  });
  const [minute, setMinute] = useState<number>(() => {
    if (!value) return 0;
    return parseInt(value.split(":")[1] || "0", 10);
  });

  useEffect(() => {
    if (value) {
      const [h, m] = value.split(":").map((x) => parseInt(x, 10));
      setPeriod(h >= 12 ? "PM" : "AM");
      setHour12(h % 12 || 12);
      setMinute(m);
    }
  }, [value]);

  const minutes = useMemo(() => {
    const out: number[] = [];
    for (let m = 0; m < 60; m += minuteStep) out.push(m);
    return out;
  }, [minuteStep]);
  const hours = useMemo(() => Array.from({ length: 12 }, (_, i) => i + 1), []);

  function fmt12(hm24?: string): string {
    if (!hm24) return placeholder;
    const [h, m] = hm24.split(":").map((x) => parseInt(x, 10));
    const p = h >= 12 ? "PM" : "AM";
    const h12 = h % 12 || 12;
    return `${String(h12).padStart(2, "0")}:${String(m).padStart(2, "0")} ${p}`;
  }

  function apply() {
    let h24 = hour12 % 12; // 12 → 0
    if (period === "PM") h24 += 12;
    const out = `${String(h24).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
    onChange(out);
    setOpen(false);
  }

  const display = fmt12(value);

  return (
    <View style={{ marginBottom: 12 }}>
      {label ? <Txt variant="label" style={styles.label}>{label}</Txt> : null}
      <TouchableOpacity testID={testID || "time-picker-trigger"} style={styles.trigger} onPress={() => setOpen(true)} activeOpacity={0.8}>
        <Ionicons name="time" size={20} color={colors.textSecondary} />
        <Txt style={{ marginLeft: 10, color: value ? colors.textPrimary : colors.textSecondary, flex: 1 }}>
          {display}
        </Txt>
        <Ionicons name="chevron-down" size={18} color={colors.textSecondary} />
      </TouchableOpacity>

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <View style={styles.modalBg}>
          <View style={styles.sheet}>
            <View style={styles.sheetHeader}>
              <Txt variant="h2">{label || "Select time"}</Txt>
              <TouchableOpacity onPress={() => setOpen(false)}>
                <Ionicons name="close" size={26} color={colors.textPrimary} />
              </TouchableOpacity>
            </View>
            <View style={styles.preview}>
              <Txt style={{ fontSize: 28, fontWeight: "800" }}>
                {String(hour12).padStart(2, "0")}:{String(minute).padStart(2, "0")} {period}
              </Txt>
            </View>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <View style={{ flex: 1 }}>
                <Txt variant="label" style={{ marginBottom: 4 }}>Hour</Txt>
                <FlatList
                  data={hours}
                  keyExtractor={(n) => `h-${n}`}
                  style={styles.scroller}
                  renderItem={({ item }) => {
                    const sel = item === hour12;
                    return (
                      <TouchableOpacity testID={`hour-${item}`} style={[styles.pickRow, sel && styles.pickRowSel]} onPress={() => setHour12(item)}>
                        <Txt style={{ color: sel ? "#fff" : colors.textPrimary, fontWeight: sel ? "700" : "500" }}>{String(item).padStart(2, "0")}</Txt>
                      </TouchableOpacity>
                    );
                  }}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Txt variant="label" style={{ marginBottom: 4 }}>Minute</Txt>
                <FlatList
                  data={minutes}
                  keyExtractor={(n) => `m-${n}`}
                  style={styles.scroller}
                  renderItem={({ item }) => {
                    const sel = item === minute;
                    return (
                      <TouchableOpacity testID={`minute-${item}`} style={[styles.pickRow, sel && styles.pickRowSel]} onPress={() => setMinute(item)}>
                        <Txt style={{ color: sel ? "#fff" : colors.textPrimary, fontWeight: sel ? "700" : "500" }}>{String(item).padStart(2, "0")}</Txt>
                      </TouchableOpacity>
                    );
                  }}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Txt variant="label" style={{ marginBottom: 4 }}>AM / PM</Txt>
                <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md }}>
                  {(["AM", "PM"] as const).map((p) => {
                    const sel = p === period;
                    return (
                      <TouchableOpacity key={p} testID={`period-${p}`} style={[styles.pickRow, sel && styles.pickRowSel]} onPress={() => setPeriod(p)}>
                        <Txt style={{ color: sel ? "#fff" : colors.textPrimary, fontWeight: sel ? "700" : "500" }}>{p}</Txt>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>
            </View>
            <View style={{ flexDirection: "row", gap: 8, marginTop: 14 }}>
              <Button title="Cancel" variant="secondary" onPress={() => setOpen(false)} style={{ flex: 1 }} />
              <Button testID="time-apply" title="Apply" onPress={apply} style={{ flex: 1 }} />
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  label: { marginBottom: 6 },
  trigger: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: 12,
    paddingVertical: Platform.OS === "ios" ? 14 : 12,
    backgroundColor: colors.surface,
    flexDirection: "row",
    alignItems: "center",
  },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.bg, padding: 20, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: "85%" },
  sheetHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
  row: { paddingHorizontal: 14, paddingVertical: 14, borderRadius: radius.md, marginVertical: 2, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  rowSelected: { backgroundColor: colors.primary },
  preview: { alignItems: "center", paddingVertical: 14, backgroundColor: colors.surface, borderRadius: radius.md, marginBottom: 12 },
  scroller: { maxHeight: 220, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md },
  pickRow: { paddingVertical: 12, paddingHorizontal: 14, alignItems: "center" },
  pickRowSel: { backgroundColor: colors.primary },
});
