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
import { successAlert } from "@/src/lib/successAlert";

const COIN =
  "https://static.prod-images.emergentagent.com/jobs/d2f455eb-160b-40ff-9a4e-1d583c1869b0/images/9e5ea04b28cbe7d19560f639172fa32c7ea2e010c38001356192231f7835193d.png";

function txLabel(t: any): string {
  if (t?.meta?.label) return t.meta.label;
  const map: Record<string, string> = {
    signup_bonus: "Signup Bonus",
    deposit: "Top up",
    apply: "Job Application",
    book: "Mock Interview Booking",
    refund: "Refund",
    interview_reward: "Interview Reward",
    hiring_reward: "Hiring Reward",
    redemption_locked: "Redemption Hold",
    redemption_refunded: "Redemption Refund",
    redemption_paid: "Redemption Paid",
  };
  return map[t?.reason] || (t?.reason || "").replace(/_/g, " ");
}

export default function StudentWallet() {
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [plans, setPlans] = useState<any>(null);
  const [amount, setAmount] = useState("199");
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [w, p] = await Promise.all([api("/wallet"), api("/subscription/plans")]);
      setData(w);
      setPlans(p);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function buyCredits() {
    const amt = parseInt(amount, 10);
    if (!amt || amt < 1) return Alert.alert("Invalid amount");
    setSubmitting(true);
    try {
      const order = await api<any>("/wallet/deposit/create-order", {
        method: "POST",
        body: { amount_inr: amt },
      });
      const r = await api<any>("/wallet/deposit/confirm", {
        method: "POST",
        body: {
          razorpay_order_id: order.razorpay_order_id,
          razorpay_payment_id: `pay_mock_${Date.now()}`,
          razorpay_signature: "mock_sig",
        },
      });
      successAlert.show({
        title: "Payment Successful",
        message: `${r.added} credits have been added to your wallet. New balance: ${r.credits}.`,
      });
      load();
    } catch (e: any) {
      Alert.alert("Payment failed", e.message);
    } finally {
      setSubmitting(false);
    }
  }

  const credits = data?.credits ?? 0;
  // Format with Indian thousand separators and pick a font size that fits up to 8 digits
  const creditsLabel = (credits || 0).toLocaleString("en-IN");
  const balanceFont =
    creditsLabel.length <= 4 ? 52 :
    creditsLabel.length <= 6 ? 42 :
    creditsLabel.length <= 8 ? 34 : 28;

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Stack.Screen options={{ headerShown: false }} />

      {/* Top header with back button */}
      <View style={styles.header}>
        <TouchableOpacity testID="wallet-back-btn" onPress={() => router.back()} style={styles.backBtn} hitSlop={10}>
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </TouchableOpacity>
        <Txt variant="h1" style={{ marginLeft: 10 }}>Wallet</Txt>
      </View>

      {/* Prominent balance hero */}
      <LinearGradient
        colors={["#FF5A5F", "#FFB347"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.hero}
      >
        <View style={styles.heroContent}>
          <Txt
            variant="label"
            style={{ color: "#fff", opacity: 0.9, letterSpacing: 1 }}
            numberOfLines={1}
            adjustsFontSizeToFit
            minimumFontScale={0.7}
          >
            AVAILABLE CREDITS
          </Txt>
          <Txt
            style={[styles.balanceNumber, { fontSize: balanceFont, lineHeight: balanceFont + 4 }]}
            testID="wallet-credits"
            numberOfLines={1}
            adjustsFontSizeToFit
            minimumFontScale={0.4}
            allowFontScaling={false}
          >
            {creditsLabel}
          </Txt>
        </View>
        <Image source={{ uri: COIN }} style={styles.heroCoin} resizeMode="contain" />
      </LinearGradient>

      {/* Top up / Buy credits — preserved functionality (Razorpay mock + first-deposit offer) */}
      <Card highlight style={{ marginTop: 16 }}>
        <Txt variant="label" style={{ color: colors.primary }}>
          {plans?.paid_tier?.is_first_deposit ? "First-time offer 🎉" : "Top up"}
        </Txt>
        <Txt variant="h2" style={{ marginTop: 4 }}>
          {plans?.paid_tier?.is_first_deposit
            ? `₹${plans?.paid_tier?.first_deposit_inr} → ${plans?.paid_tier?.first_deposit_credits} credits`
            : "1 INR = 1 credit"}
        </Txt>
        <Input
          testID="deposit-amount"
          label="Amount (INR)"
          keyboardType="number-pad"
          value={amount}
          onChangeText={setAmount}
          style={{ marginTop: 12 }}
        />
        <Button
          testID="buy-credits"
          title={`Buy credits — ₹${amount || 0}`}
          loading={submitting}
          onPress={buyCredits}
          icon={<Ionicons name="card" size={18} color="#fff" />}
        />
      </Card>

      <Txt variant="h3" style={{ marginTop: 24, marginBottom: 8 }}>Transactions</Txt>
      {!data?.transactions || data.transactions.length === 0 ? (
        <Txt variant="muted">No transactions yet.</Txt>
      ) : null}
      <View style={{ gap: 8 }}>
        {(data?.transactions || []).map((t: any) => (
          <Card key={t.id} padding={12}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <View style={{ flex: 1 }}>
                <Txt style={{ fontWeight: "600" }}>{txLabel(t)}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>
                  {new Date(t.created_at).toLocaleString()}
                </Txt>
              </View>
              <Txt style={{ fontWeight: "800", color: t.delta >= 0 ? colors.success : colors.error }}>
                {t.delta >= 0 ? "+" : ""}
                {t.delta}
              </Txt>
            </View>
          </Card>
        ))}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", marginBottom: 10 },
  backBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  hero: {
    padding: 20,
    borderRadius: radius.xxl,
    flexDirection: "row",
    alignItems: "center",
    minHeight: 130,
  },
  heroContent: { flex: 1, minWidth: 0, paddingRight: 8 },
  heroCoin: { width: 80, height: 80, marginLeft: 8 },
  balanceNumber: {
    color: "#fff",
    fontWeight: "900",
    marginTop: 6,
  },
});
