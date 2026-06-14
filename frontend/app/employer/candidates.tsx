import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Alert } from "react-native";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { ScreenTitle } from "@/src/components/ScreenTitle";

export default function Candidates() {
  const [apps, setApps] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const a = await api<any[]>("/applications");
      setApps(a);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function hire(id: string) {
    try {
      await api("/applications/hire", { method: "POST", body: { application_id: id } });
      Alert.alert("Hired", "Referrer (if any) earned +500 credits.");
      load();
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    }
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <ScreenTitle
        title="Candidates"
        icon="people"
        color="#2563EB"
        subtitle={`${apps.length} application${apps.length === 1 ? "" : "s"}`}
      />
      <View style={{ marginTop: 16, gap: 12 }}>
        {apps.length === 0 ? <Txt variant="muted">No candidates yet.</Txt> : null}
        {apps.map((a) => (
          <Card key={a.id}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <View style={{ flex: 1 }}>
                <Txt variant="h3">{a.student_name}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>{a.job_title}</Txt>
                {a.referrer_pro_name ? <Txt variant="small" style={{ color: "#7C3AED", marginTop: 2 }}>⭐ Referred by {a.referrer_pro_name}</Txt> : null}
              </View>
              <View style={[styles.pill, { backgroundColor: pillColor(a.status) }]}>
                <Txt variant="small" style={{ color: "#fff", fontWeight: "700", textTransform: "capitalize" }}>{a.status}</Txt>
              </View>
            </View>
            {a.status !== "hired" ? (
              <Button testID={`hire-${a.id}`} title="Mark hired" onPress={() => hire(a.id)} style={{ marginTop: 12 }} />
            ) : null}
          </Card>
        ))}
      </View>
    </Screen>
  );
}

function pillColor(s: string) {
  if (s === "hired") return colors.success;
  if (s === "referred") return "#7C3AED";
  return colors.accent;
}

const styles = StyleSheet.create({ pill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 } });
