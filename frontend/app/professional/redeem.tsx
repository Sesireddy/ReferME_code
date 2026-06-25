import React, { useEffect, useState } from "react";
import { View, StyleSheet, Alert, TouchableOpacity, ScrollView } from "react-native";
import { useRouter, Stack } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

const MIN_CREDITS = 500;
const INR_PER_CREDIT = 1;

function validUpi(upi: string): boolean {
  return /^[\w.\-_]{2,256}@[a-zA-Z]{2,64}$/.test((upi || "").trim());
}

export default function RedeemCredits() {
  const router = useRouter();
  const [avail, setAvail] = useState(0);
  const [locked, setLocked] = useState(0);
  const [credits, setCredits] = useState(String(MIN_CREDITS));
  const [holder, setHolder] = useState("");
  const [upi, setUpi] = useState("");
  const [bank, setBank] = useState("");
  const [ifsc, setIfsc] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const w = await api<any>("/wallet");
        setAvail(w?.credits ?? 0);
        setLocked(w?.locked_credits ?? 0);
        // Prefill with all available rounded to nearest hundred (capped at avail) if >= 500
        if ((w?.credits ?? 0) >= MIN_CREDITS) {
          setCredits(String(w.credits));
        }
      } catch {}
      setLoading(false);
    })();
  }, []);

  const creditsNum = parseInt(credits, 10) || 0;
  const amountINR = +(creditsNum * INR_PER_CREDIT).toFixed(2);
  const isEligible = avail >= MIN_CREDITS;
  const canSubmit =
    isEligible &&
    creditsNum >= MIN_CREDITS &&
    creditsNum <= avail &&
    holder.trim().length >= 2 &&
    validUpi(upi);

  async function submit() {
    if (creditsNum < MIN_CREDITS) {
      return Alert.alert("Below minimum", `Minimum ${MIN_CREDITS} credits are required to submit a redemption request.`);
    }
    if (creditsNum > avail) {
      return Alert.alert("Insufficient credits", "Redeem credits cannot exceed available credits.");
    }
    if (!validUpi(upi)) {
      return Alert.alert("Invalid UPI ID", "Please enter a valid UPI ID (e.g. yourname@bank).");
    }
    if (holder.trim().length < 2) {
      return Alert.alert("Missing details", "Please enter the account holder name.");
    }
    setSubmitting(true);
    try {
      await api("/redemption/submit", {
        method: "POST",
        body: {
          credits: creditsNum,
          account_holder_name: holder.trim(),
          upi_id: upi.trim(),
          bank_account: bank.trim() || "",
          ifsc: ifsc.trim() || "",
        },
      });
      Alert.alert(
        "Request submitted",
        `Your redemption request for ${creditsNum} credits (₹${amountINR}) is now pending approval.`,
        [{ text: "OK", onPress: () => router.replace("/professional/wallet") }],
      );
    } catch (e: any) {
      Alert.alert("Submission failed", e.message || "Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Screen>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.headerRow}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} hitSlop={10}>
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </TouchableOpacity>
        <View style={{ flexDirection: "row", alignItems: "center", marginLeft: 10 }}>
          <View style={styles.iconBubble}>
            <Ionicons name="cash" size={22} color="#7C3AED" />
          </View>
          <Txt variant="h1" style={{ marginLeft: 8 }}>Redeem Credits</Txt>
        </View>
      </View>

      <Card style={styles.summaryCard}>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <View>
            <Txt variant="label" style={{ color: "#fff", opacity: 0.85 }}>Available Credits</Txt>
            <Txt style={styles.bigNum} numberOfLines={1} adjustsFontSizeToFit testID="redeem-available">{avail}</Txt>
          </View>
          <View style={{ alignItems: "flex-end" }}>
            <Txt variant="label" style={{ color: "#fff", opacity: 0.85 }}>Locked</Txt>
            <Txt style={[styles.bigNum, { fontSize: 24 }]} testID="redeem-locked">{locked}</Txt>
          </View>
        </View>
        <Txt style={{ color: "#fff", marginTop: 6, opacity: 0.95 }}>
          ₹{Math.floor(avail * INR_PER_CREDIT)} payout value · 1 credit = ₹1
        </Txt>
      </Card>

      {!isEligible ? (
        <Card style={[styles.noticeCard, { borderColor: colors.warning }]}>
          <View style={{ flexDirection: "row", alignItems: "center" }}>
            <Ionicons name="alert-circle" size={20} color={colors.warning} />
            <Txt style={{ marginLeft: 8, color: colors.warning, fontWeight: "700" }}>Not yet eligible</Txt>
          </View>
          <Txt variant="small" style={{ marginTop: 4 }}>
            Minimum {MIN_CREDITS} credits are required to submit a redemption request. Earn more credits by conducting mock interviews and successful referrals.
          </Txt>
        </Card>
      ) : null}

      <Card style={{ marginTop: 12 }}>
        <Txt variant="h3">Redemption Details</Txt>

        <Input
          testID="redeem-credits"
          label="Credits to Redeem"
          keyboardType="number-pad"
          value={credits}
          onChangeText={(t) => setCredits(t.replace(/[^0-9]/g, ""))}
        />
        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: -8, marginBottom: 6 }}>
          Equivalent payout: ₹{amountINR}
        </Txt>

        <Input
          testID="redeem-holder"
          label="Account Holder Name"
          value={holder}
          onChangeText={setHolder}
          autoCapitalize="words"
        />

        <Input
          testID="redeem-upi"
          label="UPI ID"
          placeholder="yourname@bank"
          value={upi}
          onChangeText={setUpi}
          autoCapitalize="none"
        />

        <Input
          testID="redeem-bank"
          label="Bank Account Number (Optional)"
          keyboardType="number-pad"
          value={bank}
          onChangeText={setBank}
        />

        <Input
          testID="redeem-ifsc"
          label="IFSC Code (Optional)"
          value={ifsc}
          onChangeText={(t) => setIfsc(t.toUpperCase())}
          autoCapitalize="characters"
        />

        <Button
          testID="redeem-submit"
          title="Submit Redemption Request"
          loading={submitting}
          disabled={!canSubmit || loading}
          onPress={submit}
          icon={<Ionicons name="paper-plane" size={18} color="#fff" />}
        />

        {!canSubmit && isEligible ? (
          <Txt variant="small" style={{ marginTop: 8, color: colors.warning }}>
            Please fill credits ≥ {MIN_CREDITS}, holder name, and a valid UPI ID to enable submission.
          </Txt>
        ) : null}
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "center", marginBottom: 8 },
  backBtn: {
    width: 40, height: 40, borderRadius: 20,
    alignItems: "center", justifyContent: "center",
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
  },
  iconBubble: {
    width: 40, height: 40, borderRadius: 12,
    alignItems: "center", justifyContent: "center",
    backgroundColor: "#7C3AED1F",
  },
  summaryCard: {
    backgroundColor: "#7C3AED",
    padding: 18,
    borderRadius: radius.xxl,
    marginTop: 8,
  },
  bigNum: { color: "#fff", fontSize: 36, fontWeight: "800", marginTop: 4 },
  noticeCard: { marginTop: 12, borderWidth: 1, padding: 12 },
});
