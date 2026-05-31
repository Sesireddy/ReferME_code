import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Alert } from "react-native";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function AdminPayouts() {
  const [payouts, setPayouts] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const p = await api<any[]>("/payouts");
      setPayouts(p);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function act(id: string, action: "approve" | "reject") {
    try {
      await api("/admin/payouts/action", { method: "POST", body: { payout_id: id, action, note: action === "reject" ? "Insufficient KYC" : "" } });
      load();
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    }
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Txt variant="h1">Payouts</Txt>
      <View style={{ marginTop: 16, gap: 8 }}>
        {payouts.length === 0 ? <Txt variant="muted">No payouts yet.</Txt> : null}
        {payouts.map((p) => (
          <Card key={p.id}>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <View style={{ flex: 1 }}>
                <Txt variant="h3">{p.professional_name} — ₹{p.amount_inr}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>{p.upi_or_account}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>{new Date(p.created_at).toLocaleString()}</Txt>
              </View>
              <View style={[styles.pill, { backgroundColor: pillColor(p.status) }]}>
                <Txt variant="small" style={{ color: "#fff", fontWeight: "700", textTransform: "capitalize" }}>{p.status}</Txt>
              </View>
            </View>
            {p.status === "requested" ? (
              <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
                <Button testID={`approve-${p.id}`} title="Approve" onPress={() => act(p.id, "approve")} style={{ flex: 1 }} />
                <Button testID={`reject-${p.id}`} title="Reject" variant="outline" onPress={() => act(p.id, "reject")} style={{ flex: 1 }} />
              </View>
            ) : null}
          </Card>
        ))}
      </View>
    </Screen>
  );
}
function pillColor(s: string) {
  if (s === "approved") return colors.success;
  if (s === "rejected") return colors.error;
  return colors.accent;
}
const styles = StyleSheet.create({ pill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 } });
