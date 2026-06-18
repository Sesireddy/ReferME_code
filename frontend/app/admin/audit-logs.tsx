import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, ScrollView, TouchableOpacity, Alert } from "react-native";
import { useRouter, Stack } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Input } from "@/src/components/Input";
import { ScreenTitle } from "@/src/components/ScreenTitle";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

type AuditLog = {
  id: string;
  actor_email: string;
  actor_name: string;
  action: string;
  entity_type: string;
  entity_id: string;
  reason?: string;
  diff?: Record<string, { before: any; after: any }>;
  extra?: Record<string, any>;
  created_at: string;
  purge_at?: string;
};

const ACTION_LABEL: Record<string, string> = {
  "user.edit": "User Edited",
  "user.credits.adjust": "Credits Adjusted",
  "job.edit": "Job Edited",
  "interview_booking.cancel": "Booking Cancelled",
};

const ACTION_ICON: Record<string, any> = {
  "user.edit": "person",
  "user.credits.adjust": "cash",
  "job.edit": "briefcase",
  "interview_booking.cancel": "close-circle",
};

const ACTION_COLOR: Record<string, string> = {
  "user.edit": "#2563EB",
  "user.credits.adjust": colors.success,
  "job.edit": "#7C3AED",
  "interview_booking.cancel": colors.error,
};

const ENTITY_FILTERS = [
  { key: "", label: "All" },
  { key: "user", label: "Users" },
  { key: "credit_adjustment", label: "Credits" },
  { key: "job", label: "Jobs" },
  { key: "interview_booking", label: "Bookings" },
];

function formatValue(v: any): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export default function AdminAuditLogs() {
  const router = useRouter();
  const [items, setItems] = useState<AuditLog[]>([]);
  const [retention, setRetention] = useState(90);
  const [q, setQ] = useState("");
  const [entity, setEntity] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (entity) params.set("entity", entity);
      if (q.trim()) params.set("q", q.trim());
      params.set("limit", "200");
      const data = await api<any>(`/admin/audit-logs?${params.toString()}`);
      setItems(data?.items || []);
      if (data?.retention_days_for_jobs_and_interviews) {
        setRetention(data.retention_days_for_jobs_and_interviews);
      }
    } catch (e: any) {
      Alert.alert("Failed", e.message || "Could not load audit logs.");
    } finally {
      setRefreshing(false);
    }
  }, [entity, q]);

  useEffect(() => { load(); }, [load]);

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} hitSlop={10}>
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </TouchableOpacity>
        <View style={{ flex: 1, marginLeft: 8 }}>
          <ScreenTitle
            title="Audit Logs"
            icon="time"
            color={colors.admin || colors.primary}
            subtitle={`Jobs & Interview entries auto-purge after ${retention} days. Users & Credits kept forever.`}
          />
        </View>
      </View>

      <Input
        testID="audit-search"
        placeholder="Search by actor, target email, reason, entity id…"
        value={q}
        onChangeText={setQ}
      />

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {ENTITY_FILTERS.map((t) => {
          const active = entity === t.key;
          return (
            <TouchableOpacity
              key={t.key || "all"}
              testID={`entity-${t.key || "all"}`}
              onPress={() => setEntity(t.key)}
              style={[styles.tab, active && styles.tabActive]}
              activeOpacity={0.7}
            >
              <Txt style={[styles.tabLabel, active && { color: "#fff" }]}>{t.label}</Txt>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <View style={{ marginTop: 12, gap: 8 }}>
        {items.length === 0 ? (
          <Card style={{ paddingVertical: 24, alignItems: "center" }}>
            <Ionicons name="document-text" size={32} color={colors.textSecondary} />
            <Txt variant="muted" style={{ marginTop: 6 }}>No audit log entries.</Txt>
          </Card>
        ) : null}

        {items.map((it) => {
          const c = ACTION_COLOR[it.action] || colors.textSecondary;
          const ic = ACTION_ICON[it.action] || "checkmark-done";
          const willPurge = !!it.purge_at;
          return (
            <Card key={it.id} padding={14}>
              <View style={{ flexDirection: "row", alignItems: "flex-start" }}>
                <View style={[styles.iconBubble, { backgroundColor: c + "1F" }]}>
                  <Ionicons name={ic} size={18} color={c} />
                </View>
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", flexWrap: "wrap" }}>
                    <Txt style={{ fontWeight: "700" }}>{ACTION_LABEL[it.action] || it.action}</Txt>
                    {willPurge ? (
                      <View style={styles.purgeTag}>
                        <Ionicons name="hourglass" size={10} color={colors.warning} />
                        <Txt style={{ color: colors.warning, fontSize: 10, fontWeight: "700", marginLeft: 2 }}>auto-purge</Txt>
                      </View>
                    ) : (
                      <View style={[styles.purgeTag, { backgroundColor: colors.success + "1A", borderColor: colors.success }]}>
                        <Ionicons name="infinite" size={10} color={colors.success} />
                        <Txt style={{ color: colors.success, fontSize: 10, fontWeight: "700", marginLeft: 2 }}>kept</Txt>
                      </View>
                    )}
                  </View>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }} numberOfLines={1}>
                    by {it.actor_name || it.actor_email} · {new Date(it.created_at).toLocaleString()}
                  </Txt>
                  {it.extra?.target_email ? (
                    <Txt variant="small" style={{ color: colors.textSecondary }} numberOfLines={1}>
                      Target: {it.extra.target_email}
                    </Txt>
                  ) : null}
                  {it.extra?.job_title ? (
                    <Txt variant="small" style={{ color: colors.textSecondary }} numberOfLines={1}>
                      Job: {it.extra.job_title}
                    </Txt>
                  ) : null}
                  {/* Diff */}
                  {it.diff && Object.keys(it.diff).length > 0 ? (
                    <View style={styles.diffBlock}>
                      {Object.entries(it.diff).map(([k, v]: [string, any]) => (
                        <Txt key={k} variant="small" style={{ fontFamily: "monospace" as any, color: colors.textPrimary }} numberOfLines={2}>
                          {k}: <Txt style={{ color: colors.error }}>{formatValue(v.before)}</Txt> → <Txt style={{ color: colors.success, fontWeight: "700" }}>{formatValue(v.after)}</Txt>
                        </Txt>
                      ))}
                    </View>
                  ) : null}
                  {/* Extra delta */}
                  {it.extra?.delta !== undefined ? (
                    <Txt variant="small" style={{ marginTop: 4, color: (it.extra.delta as number) > 0 ? colors.success : colors.error, fontWeight: "700" }}>
                      Δ {it.extra.delta > 0 ? "+" : ""}{it.extra.delta} credits
                    </Txt>
                  ) : null}
                  {it.reason ? (
                    <Txt variant="small" style={{ marginTop: 6, fontStyle: "italic", color: colors.textSecondary }} numberOfLines={3}>
                      “{it.reason}”
                    </Txt>
                  ) : null}
                </View>
              </View>
            </Card>
          );
        })}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", marginBottom: 8 },
  backBtn: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  tab: { backgroundColor: colors.surface, borderRadius: 18, paddingHorizontal: 12, paddingVertical: 7, borderWidth: 1, borderColor: colors.border },
  tabActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  tabLabel: { fontSize: 12, fontWeight: "600", color: colors.textSecondary },
  iconBubble: { width: 36, height: 36, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  purgeTag: {
    marginLeft: 6,
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.warning + "1A",
    borderColor: colors.warning,
    borderWidth: 1,
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 8,
  },
  diffBlock: {
    marginTop: 8,
    padding: 8,
    backgroundColor: colors.surfaceAlt || "#F9FAFB",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 2,
  },
});
