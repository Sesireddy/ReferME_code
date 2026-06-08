import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Image, Alert, TouchableOpacity } from "react-native";
import { useRouter, Stack } from "expo-router";
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

export default function ProWallet() {
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [plans, setPlans] = useState<any>(null);
  const [amount, setAmount] = useState("199");
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);  // collapsed by default

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

  const txs = data?.transactions || [];
  const earnedToday = txs.filter((t: any) => t.delta > 0).reduce((s: number, t: any) => s + t.delta, 0);

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Stack.Screen options={{ headerShown: true, title: "Wallet" }} />
      <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 6 }}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </TouchableOpacity>
        <Txt variant="h1" style={{ marginLeft: 10 }}>Wallet</Txt>
      </View>

      <LinearGradient
        colors={["#7C3AED", "#A855F7"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.hero}
      >
        <View style={{ flex: 1 }}>
          <Txt variant="label" style={{ color: "#fff", opacity: 0.85 }}>Available Credits</Txt>
          <Txt style={{ color: "#fff", fontSize: 48, fontWeight: "800", marginTop: 4 }} testID="wallet-credits">
            {data?.credits ?? 0}
          </Txt>
          <Txt style={{ color: "#fff", opacity: 0.9 }}>
            ₹{Math.floor((data?.credits ?? 0) / 2)} payout value · {earnedToday > 0 ? `+${earnedToday} earned` : "Keep referring!"}
          </Txt>
        </View>
        <Image source={{ uri: COIN }} style={{ width: 100, height: 100 }} />
      </LinearGradient>

      <Card highlight style={{ marginTop: 16 }}>
        <Txt variant="label" style={{ color: colors.primary }}>How you earn</Txt>
        <View style={{ marginTop: 6 }}>
          <Txt variant="small">• +35 credits per successful mock interview</Txt>
          <Txt variant="small">• +100 credits on 4 valid applications to a job you posted</Txt>
          <Txt variant="small">• +1500 credits when a candidate you hire is verified</Txt>
        </View>
      </Card>

      <Card style={{ marginTop: 12 }}>
        <Txt variant="h3">Top up</Txt>
        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>
          Each action (apply / book) costs {plans?.paid_tier?.action_cost ?? 49} credits.
        </Txt>
        <Input testID="deposit-amount" label="Amount (INR)" keyboardType="number-pad" value={amount} onChangeText={setAmount} />
        <Button testID="buy-credits" title={`Buy credits — ₹${amount || 0}`} loading={submitting} onPress={buyCredits} />
      </Card>

      <TouchableOpacity testID="toggle-history" onPress={() => setHistoryOpen((v) => !v)} style={styles.historyHeader}>
        <Txt variant="h3">View Credit History</Txt>
        <Ionicons name={historyOpen ? "chevron-up" : "chevron-down"} size={22} color={colors.textSecondary} />
      </TouchableOpacity>

      {historyOpen ? (
        <View style={{ marginTop: 8, gap: 8 }}>
          {txs.length === 0 ? <Txt variant="muted">No transactions yet.</Txt> : null}
          {txs.map((t: any) => (
            <Card key={t.id} padding={12}>
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                <View style={{ flex: 1 }}>
                  <Txt style={{ fontWeight: "600", textTransform: "capitalize" }}>
                    {(t.reason || "").replace(/_/g, " ")}
                  </Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary }}>
                    {new Date(t.created_at).toLocaleString()}
                  </Txt>
                  {t.meta?.candidate_name ? (
                    <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                      {t.meta.candidate_name}{t.meta?.job_title ? ` · ${t.meta.job_title}` : ""}
                    </Txt>
                  ) : null}
                </View>
                <Txt style={{ fontWeight: "800", color: t.delta >= 0 ? colors.success : colors.error }}>
                  {t.delta >= 0 ? "+" : ""}{t.delta}
                </Txt>
              </View>
            </Card>
          ))}
        </View>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  backBtn: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  hero: { marginTop: 6, padding: 20, borderRadius: radius.xxl, flexDirection: "row", alignItems: "center" },
  historyHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 24, paddingVertical: 10 },
});
