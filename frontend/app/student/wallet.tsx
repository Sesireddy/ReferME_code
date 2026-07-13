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
    first_deposit_bonus: "First Deposit Bonus (50%)",
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
  const [amount, setAmount] = useState("200");
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

  const isFirstDeposit: boolean = !!plans?.paid_tier?.is_first_deposit;
  const firstMin: number = plans?.paid_tier?.first_deposit_inr ?? 200;
  const bonusPct: number = plans?.paid_tier?.first_deposit_bonus_percent ?? 50;
  const bonusMax: number = plans?.paid_tier?.first_deposit_bonus_max_credits ?? 5000;

  // Preview computation (kept in-sync with backend rule)
  const previewAmt = parseInt(amount, 10) || 0;
  const previewEligible = isFirstDeposit && previewAmt >= firstMin;
  const previewBonus = previewEligible
    ? Math.min(Math.floor((previewAmt * bonusPct) / 100), bonusMax)
    : 0;
  const previewTotal = previewAmt + previewBonus;

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
      if (r.first_deposit_bonus_applied) {
        successAlert.show({
          title: "🎉 First Deposit Bonus Applied!",
          message:
            `Base credits: +${r.base_credits}\n` +
            `Bonus credits: +${r.bonus_credits} (${bonusPct}% off ₹${amt})\n` +
            `Total added: +${r.added}\n\n` +
            `New balance: ${r.credits}`,
        });
      } else {
        successAlert.show({
          title: "Payment Successful",
          message: `${r.added} credits have been added to your wallet. New balance: ${r.credits}.`,
        });
      }
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

      {/* First deposit promotional banner — only for eligible users */}
      {isFirstDeposit ? (
        <LinearGradient
          colors={["#16A34A", "#22C55E"]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.offerBanner}
        >
          <View style={styles.offerIcon}>
            <Txt style={{ fontSize: 22 }}>🎉</Txt>
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Txt style={styles.offerTitle} numberOfLines={1}>
              First Deposit — {bonusPct}% Bonus!
            </Txt>
            <Txt style={styles.offerSubtitle}>
              Deposit ≥ ₹{firstMin} and get {bonusPct}% extra credits (up to +{bonusMax}).
            </Txt>
          </View>
        </LinearGradient>
      ) : null}

      {/* Top up / Buy credits — preserved functionality (Razorpay mock + first-deposit offer) */}
      <Card highlight style={{ marginTop: 16 }}>
        <Txt variant="label" style={{ color: colors.primary }}>
          {isFirstDeposit ? "First-time offer 🎉" : "Top up"}
        </Txt>
        <Txt variant="h2" style={{ marginTop: 4 }}>
          {isFirstDeposit
            ? `₹${firstMin}+ → +${bonusPct}% bonus credits`
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
        {/* Live bonus preview for first-time depositors */}
        {isFirstDeposit && previewAmt > 0 ? (
          previewEligible ? (
            <View style={styles.previewBox}>
              <Txt style={{ fontSize: 12, color: "#065F46", fontWeight: "700" }}>
                Base: {previewAmt} + Bonus: {previewBonus} = {previewTotal} credits
              </Txt>
            </View>
          ) : (
            <View style={[styles.previewBox, { backgroundColor: "#FEF3C7", borderColor: "#F59E0B" }]}>
              <Txt style={{ fontSize: 12, color: "#92400E", fontWeight: "700" }}>
                Add ₹{firstMin - previewAmt} more to unlock the {bonusPct}% bonus.
              </Txt>
            </View>
          )
        ) : null}
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
  offerBanner: {
    marginTop: 12,
    padding: 14,
    borderRadius: radius.xxl,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  offerIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "rgba(255,255,255,0.25)",
    alignItems: "center",
    justifyContent: "center",
  },
  offerTitle: {
    color: "#fff",
    fontSize: 15,
    fontWeight: "800",
  },
  offerSubtitle: {
    color: "#fff",
    opacity: 0.95,
    fontSize: 12,
    marginTop: 2,
  },
  previewBox: {
    marginTop: 10,
    marginBottom: 4,
    padding: 10,
    borderRadius: 10,
    backgroundColor: "#D1FAE5",
    borderWidth: 1,
    borderColor: "#10B981",
  },
});
