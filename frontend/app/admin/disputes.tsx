import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Alert } from "react-native";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function AdminDisputes() {
  const [list, setList] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const d = await api<any[]>("/disputes");
      setList(d);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function resolve(id: string) {
    try {
      await api(`/admin/disputes/${id}/resolve`, { method: "POST" });
      load();
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    }
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Txt variant="h1">Disputes</Txt>
      <View style={{ marginTop: 16, gap: 8 }}>
        {list.length === 0 ? <Txt variant="muted">No disputes.</Txt> : null}
        {list.map((d) => (
          <Card key={d.id}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <View style={{ flex: 1 }}>
                <Txt variant="h3">{d.subject}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>by {d.user_email}</Txt>
              </View>
              <View style={[styles.pill, { backgroundColor: d.status === "open" ? colors.warning : colors.success }]}>
                <Txt variant="small" style={{ color: "#fff", fontWeight: "700", textTransform: "capitalize" }}>{d.status}</Txt>
              </View>
            </View>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 6 }}>{d.description}</Txt>
            {d.status === "open" ? (
              <Button testID={`resolve-${d.id}`} title="Resolve" onPress={() => resolve(d.id)} style={{ marginTop: 12 }} />
            ) : null}
          </Card>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({ pill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 } });
