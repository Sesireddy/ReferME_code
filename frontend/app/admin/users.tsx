import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet } from "react-native";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function AdminUsers() {
  const [users, setUsers] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const u = await api<any[]>("/admin/users");
      setUsers(u);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Txt variant="h1">Users</Txt>
      <Txt variant="muted">{users.length} accounts</Txt>
      <View style={{ marginTop: 16, gap: 8 }}>
        {users.map((u) => (
          <Card key={u.id} padding={14}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <View style={{ flex: 1 }}>
                <Txt variant="h3">{u.name || u.email.split("@")[0]}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>{u.email}</Txt>
              </View>
              <View style={[styles.pill, { backgroundColor: roleColor(u.role) }]}>
                <Txt variant="small" style={{ color: "#fff", fontWeight: "700", textTransform: "capitalize" }}>{u.role}</Txt>
              </View>
            </View>
            <Txt variant="small" style={{ marginTop: 6, color: colors.textSecondary }}>
              {u.credits} credits · {u.is_email_verified ? "verified" : "unverified"}
            </Txt>
          </Card>
        ))}
      </View>
    </Screen>
  );
}
function roleColor(r: string) {
  if (r === "student") return colors.primary;
  if (r === "professional") return "#7C3AED";
  if (r === "employer") return "#2563EB";
  return "#0F172A";
}
const styles = StyleSheet.create({ pill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10 } });
