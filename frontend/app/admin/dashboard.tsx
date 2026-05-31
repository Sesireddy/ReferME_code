import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet } from "react-native";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function AdminDashboard() {
  const [stats, setStats] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const s = await api("/admin/stats");
      setStats(s);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const tiles = [
    { label: "Students", value: stats?.students ?? 0, color: colors.primary },
    { label: "Professionals", value: stats?.professionals ?? 0, color: "#7C3AED" },
    { label: "Employers", value: stats?.employers ?? 0, color: "#2563EB" },
    { label: "Jobs", value: stats?.jobs ?? 0, color: colors.accent },
    { label: "Applications", value: stats?.applications ?? 0, color: colors.success },
    { label: "Interviews done", value: stats?.interviews ?? 0, color: colors.warning },
    { label: "Payouts pending", value: stats?.payouts_pending ?? 0, color: colors.error },
    { label: "Disputes open", value: stats?.disputes_open ?? 0, color: colors.error },
  ];

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Txt variant="h1">Admin</Txt>
      <Txt variant="muted">Platform overview</Txt>
      <View style={styles.grid}>
        {tiles.map((t) => (
          <Card key={t.label} style={styles.tile} padding={14}>
            <Txt variant="label" style={{ color: t.color }}>{t.label}</Txt>
            <Txt variant="h1" style={{ marginTop: 4 }}>{t.value}</Txt>
          </Card>
        ))}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 16 },
  tile: { width: "47.5%" },
});
