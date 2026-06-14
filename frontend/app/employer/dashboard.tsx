import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { ScreenTitle } from "@/src/components/ScreenTitle";

export default function EmpDashboard() {
  const router = useRouter();
  const [jobs, setJobs] = useState<any[]>([]);
  const [apps, setApps] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [j, a] = await Promise.all([api<any[]>("/jobs"), api<any[]>("/applications")]);
      setJobs(j); setApps(a);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <View style={{ flex: 1 }}>
          <ScreenTitle
            title="Jobs"
            icon="briefcase"
            color="#2563EB"
            subtitle={`${jobs.length} posted · ${apps.length} applicants`}
          />
        </View>
        <TouchableOpacity testID="notif-btn" onPress={() => router.push("/notifications")}>
          <View style={styles.iconBtn}><Ionicons name="notifications" size={22} color={colors.textPrimary} /></View>
        </TouchableOpacity>
      </View>

      <View style={{ marginTop: 16, gap: 12 }}>
        {jobs.length === 0 ? <Txt variant="muted">No jobs yet. Post one to start receiving applications.</Txt> : null}
        {jobs.map((j) => {
          const count = apps.filter((a) => a.job_id === j.id).length;
          return (
            <Card key={j.id}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <View style={{ flex: 1 }}>
                  <Txt variant="h3">{j.title}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>{j.location || "Anywhere"} · {j.salary_range || "—"}</Txt>
                </View>
                <View style={[styles.pill, { backgroundColor: colors.surfaceAlt }]}>
                  <Txt variant="small" style={{ fontWeight: "700" }}>{count} applicants</Txt>
                </View>
              </View>
              {j.bulk_openings > 1 ? <Txt variant="small" style={{ marginTop: 6, color: colors.primary, fontWeight: "700" }}>{j.bulk_openings} openings</Txt> : null}
            </Card>
          );
        })}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  iconBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  pill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 },
});
