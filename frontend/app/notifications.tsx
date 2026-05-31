import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function Notifications() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await api<any[]>("/notifications");
      setItems(r);
      await api("/notifications/read-all", { method: "POST" });
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={{ padding: 20, paddingBottom: 8, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="chevron-back" size={26} color={colors.textPrimary} />
        </TouchableOpacity>
        <Txt variant="h2">Notifications</Txt>
        <View style={{ width: 26 }} />
      </View>
      <Screen refreshing={refreshing} onRefresh={load} noPad>
        <View style={{ padding: 20, gap: 8 }}>
          {items.length === 0 ? <Txt variant="muted">No notifications yet.</Txt> : null}
          {items.map((n) => (
            <Card key={n.id} padding={14} style={!n.read ? { borderColor: colors.primary, borderWidth: 1 } : undefined}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <View style={[styles.dot, { backgroundColor: kindColor(n.kind) }]} />
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <Txt variant="h3">{n.title}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary }}>{n.body}</Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>{new Date(n.created_at).toLocaleString()}</Txt>
                </View>
              </View>
            </Card>
          ))}
        </View>
      </Screen>
    </SafeAreaView>
  );
}

function kindColor(k: string) {
  if (k === "success") return colors.success;
  if (k === "error") return colors.error;
  if (k === "warning") return colors.warning;
  return colors.primary;
}

const styles = StyleSheet.create({ dot: { width: 10, height: 10, borderRadius: 5 } });
