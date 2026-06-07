import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function ApplicationsIndex() {
  const router = useRouter();
  const [apps, setApps] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const a = await api<any[]>("/applications");
      setApps(a);
    } catch {}
    setRefreshing(false);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={["top"]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="chevron-back" size={28} color={colors.textPrimary} />
        </TouchableOpacity>
        <Txt variant="h3">My applications</Txt>
        <View style={{ width: 28 }} />
      </View>
      <Screen refreshing={refreshing} onRefresh={load} noPad>
        <View style={{ padding: 20, gap: 10 }}>
          {!loading && apps.length === 0 ? (
            <Card>
              <Txt variant="muted">No applications yet. Browse jobs and apply!</Txt>
            </Card>
          ) : null}
          {apps.map((a) => (
            <TouchableOpacity
              key={a.id}
              testID={`app-${a.id}`}
              onPress={() => router.push(`/student/applications/${a.id}`)}
              activeOpacity={0.85}
            >
              <Card>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <View style={{ flex: 1 }}>
                    <Txt variant="h3">{a.job_title}</Txt>
                    <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                      {a.referrer_pro_name ? `Referred by ${a.referrer_pro_name}` : "Direct application"}
                    </Txt>
                    <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                      Applied {new Date(a.created_at).toLocaleDateString()}
                    </Txt>
                  </View>
                  <View style={[styles.pill, { backgroundColor: statusColor(a.status) }]}>
                    <Txt variant="small" style={{ color: "#fff", fontWeight: "700", textTransform: "capitalize" }}>
                      {(a.status || "").replace(/_/g, " ")}
                    </Txt>
                  </View>
                </View>
              </Card>
            </TouchableOpacity>
          ))}
        </View>
      </Screen>
    </SafeAreaView>
  );
}

function statusColor(s: string) {
  if (s === "hired") return colors.success;
  if (s === "rejected") return colors.error;
  if (s === "referred") return "#7C3AED";
  if (s === "interview_scheduled") return colors.primary;
  if (s === "awaiting_interview") return colors.warning;
  if (s === "shortlisted") return "#2563EB";
  return colors.accent;
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border },
  pill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 },
});
