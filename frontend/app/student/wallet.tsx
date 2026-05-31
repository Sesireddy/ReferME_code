import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Image, Alert } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

const COIN = "https://static.prod-images.emergentagent.com/jobs/d2f455eb-160b-40ff-9a4e-1d583c1869b0/images/9e5ea04b28cbe7d19560f639172fa32c7ea2e010c38001356192231f7835193d.png";

export default function StudentWallet() {
  const [data, setData] = useState<any>(null);
  const [plans, setPlans] = useState<any>(null);
  const [amount, setAmount] = useState("199");
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [w, p] = await Promise.all([api("/wallet"), api("/subscription/plans")]);
      setData(w); setPlans(p);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function buyCredits() {
    const amt = parseInt(amount, 10);
    if (!amt || amt < 1) return Alert.alert("Invalid amount");
    setSubmitting(true);
    try {
      const order = await api<any>("/wallet/deposit/create-order", { method: "POST", body: { amount_inr: amt } });
      // In mock mode, immediately confirm
      const r = await api<any>("/wallet/deposit/confirm", {
        method: "POST",
        body: {
          razorpay_order_id: order.razorpay_order_id,
          razorpay_payment_id: `pay_mock_${Date.now()}`,
          razorpay_signature: "mock_sig",
        },
      });
      Alert.alert("Payment success", `+${r.added} credits added. Balance: ${r.credits}`);
      load();
    } catch (e: any) {
      Alert.alert("Payment failed", e.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Txt variant="h1">Wallet</Txt>
      <LinearGradient
        colors={["#FF5A5F", "#FFB347"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.hero}
      >
        <View style={{ flex: 1 }}>
          <Txt variant="label" style={{ color: "#fff", opacity: 0.85 }}>Balance</Txt>
          <Txt style={{ color: "#fff", fontSize: 48, fontWeight: "800", marginTop: 4 }} testID="wallet-credits">
            {data?.credits ?? 0}
          </Txt>
          <Txt style={{ color: "#fff", opacity: 0.9 }}>credits · {data?.free_uses_left ?? 0} free</Txt>
        </View>
        <Image source={{ uri: COIN }} style={{ width: 100, height: 100 }} />
      </LinearGradient>

      <Card highlight style={{ marginTop: 16 }}>
        <Txt variant="label" style={{ color: colors.primary }}>
          {plans?.paid_tier?.is_first_deposit ? "First-time offer 🎉" : "Top up"}
        </Txt>
        <Txt variant="h2" style={{ marginTop: 4 }}>
          {plans?.paid_tier?.is_first_deposit
            ? `₹${plans?.paid_tier?.first_deposit_inr} → ${plans?.paid_tier?.first_deposit_credits} credits`
            : "1 INR = 1 credit"}
        </Txt>
        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>
          Each action (apply / book) costs {plans?.paid_tier?.action_cost ?? 49} credits.
        </Txt>
        <Input testID="deposit-amount" label="Amount (INR)" keyboardType="number-pad" value={amount} onChangeText={setAmount} style={{ marginTop: 12 }} />
        <Button testID="buy-credits" title={`Buy credits — ₹${amount || 0}`} loading={submitting} onPress={buyCredits} />
      </Card>

      <Txt variant="h3" style={{ marginTop: 24, marginBottom: 8 }}>Transactions</Txt>
      {(!data?.transactions || data.transactions.length === 0) ? <Txt variant="muted">No transactions yet.</Txt> : null}
      <View style={{ gap: 8 }}>
        {(data?.transactions || []).map((t: any) => (
          <Card key={t.id} padding={12}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <View style={{ flex: 1 }}>
                <Txt style={{ fontWeight: "600", textTransform: "capitalize" }}>{(t.reason || "").replace(/_/g, " ")}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>{new Date(t.created_at).toLocaleString()}</Txt>
              </View>
              <Txt style={{ fontWeight: "800", color: t.delta >= 0 ? colors.success : colors.error }}>
                {t.delta >= 0 ? "+" : ""}{t.delta}
              </Txt>
            </View>
          </Card>
        ))}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { marginTop: 16, padding: 20, borderRadius: radius.xxl, flexDirection: "row", alignItems: "center" },
});
