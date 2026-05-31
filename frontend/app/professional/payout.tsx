import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Alert } from "react-native";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

export default function ProPayout() {
  const [user, setUser] = useState<any>(null);
  const [amount, setAmount] = useState("500");
  const [upi, setUpi] = useState("");
  const [payouts, setPayouts] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [me, p] = await Promise.all([api<{ user: any }>("/auth/me"), api<any[]>("/payouts")]);
      setUser(me.user);
      setPayouts(p);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function request() {
    const amt = parseInt(amount, 10);
    if (!upi) return Alert.alert("Enter UPI or account");
    if (!amt || amt < 500) return Alert.alert("Min ₹500 required");
    setBusy(true);
    try {
      await api("/payouts/request", { method: "POST", body: { amount_inr: amt, upi_or_account: upi } });
      Alert.alert("Requested", "Awaiting admin approval.");
      load();
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally { setBusy(false); }
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Txt variant="h1">Payouts</Txt>
      <Card style={{ marginTop: 16 }}>
        <Txt variant="label">Available credits</Txt>
        <Txt variant="h1" style={{ marginTop: 4 }} testID="pro-credits">{user?.credits ?? 0}</Txt>
        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>1 credit = ₹1 · min ₹500 redemption · admin approval required</Txt>
      </Card>

      <Card style={{ marginTop: 12 }}>
        <Txt variant="h3">Request payout</Txt>
        <Input testID="payout-amount" label="Amount (INR)" value={amount} onChangeText={setAmount} keyboardType="number-pad" />
        <Input testID="payout-upi" label="UPI / Bank account" value={upi} onChangeText={setUpi} placeholder="you@upi or A/c — IFSC" />
        <Button testID="payout-submit" title="Request payout" loading={busy} onPress={request} />
      </Card>

      <Txt variant="h3" style={{ marginTop: 24, marginBottom: 8 }}>History</Txt>
      {payouts.length === 0 ? <Txt variant="muted">No payouts yet.</Txt> : null}
      <View style={{ gap: 8 }}>
        {payouts.map((p) => (
          <Card key={p.id} padding={14}>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <View>
                <Txt variant="h3">₹{p.amount_inr}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>{new Date(p.created_at).toLocaleString()}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>{p.upi_or_account}</Txt>
              </View>
              <View style={[styles.pill, { backgroundColor: pillColor(p.status) }]}>
                <Txt variant="small" style={{ color: "#fff", fontWeight: "700", textTransform: "capitalize" }}>{p.status}</Txt>
              </View>
            </View>
            {p.admin_note ? <Txt variant="small" style={{ marginTop: 6, color: colors.textSecondary }}>Note: {p.admin_note}</Txt> : null}
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
