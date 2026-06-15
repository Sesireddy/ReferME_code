import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Image, TouchableOpacity } from "react-native";
import { useRouter, Stack } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

const COIN = "https://static.prod-images.emergentagent.com/jobs/d2f455eb-160b-40ff-9a4e-1d583c1869b0/images/9e5ea04b28cbe7d19560f639172fa32c7ea2e010c38001356192231f7835193d.png";

const MIN_REDEEM = 500;
const INR_PER_CREDIT = 0.5;

type RedemptionItem = {
  id: string;
  credits_requested: number;
  amount_inr: number;
  status: "pending" | "approved" | "paid" | "rejected";
  upi_id: string;
  payment_ref?: string;
  payment_date?: string;
  rejection_reason?: string;
  remarks?: string;
  created_at: string;
};

function statusColor(s: string): string {
  if (s === "approved") return "#2563EB";
  if (s === "paid") return colors.success;
  if (s === "rejected") return colors.error;
  return colors.warning; // pending
}

function StatusPill({ status }: { status: string }) {
  const c = statusColor(status);
  const label =
    status === "pending" ? "Pending Approval"
    : status === "approved" ? "Approved"
    : status === "paid" ? "Paid"
    : "Rejected";
  return (
    <View style={[styles.pill, { borderColor: c, backgroundColor: c + "1A" }]}>
      <Txt style={{ color: c, fontWeight: "700", fontSize: 11 }} numberOfLines={1}>{label}</Txt>
    </View>
  );
}

export default function ProWallet() {
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [reqs, setReqs] = useState<RedemptionItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [redemptionsOpen, setRedemptionsOpen] = useState(true);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [w, r] = await Promise.all([
        api<any>("/wallet"),
        api<any>("/redemption/my").catch(() => ({ items: [] })),
      ]);
      setData(w);
      setReqs(r?.items || []);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const credits = data?.credits ?? 0;
  const locked = data?.locked_credits ?? 0;
  const txs = data?.transactions || [];
  const isEligible = credits >= MIN_REDEEM;
  // Dynamic font sizing for big-balance readability
  const creditsLabel = (credits || 0).toLocaleString("en-IN");
  const balanceFont =
    creditsLabel.length <= 4 ? 52 :
    creditsLabel.length <= 6 ? 42 :
    creditsLabel.length <= 8 ? 34 : 28;

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 10 }}>
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
          {locked > 0 ? (
            <View style={styles.lockedPill}>
              <Ionicons name="lock-closed" size={12} color="#fff" />
              <Txt style={{ color: "#fff", fontSize: 11, fontWeight: "700", marginLeft: 4 }}>
                {locked} locked
              </Txt>
            </View>
          ) : null}
        </View>
        <Image source={{ uri: COIN }} style={styles.heroCoin} resizeMode="contain" />
      </LinearGradient>

      <Card highlight style={{ marginTop: 16 }}>
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          <Ionicons name="trending-up" size={18} color={colors.primary} />
          <Txt variant="label" style={{ color: colors.primary, marginLeft: 6 }}>How you earn credits</Txt>
        </View>
        <View style={{ marginTop: 6 }}>
          <Txt variant="small">• +35 credits per successful mock interview</Txt>
          <Txt variant="small">• +100 credits on 4 valid applications to a job you posted</Txt>
          <Txt variant="small">• +1500 credits when your hire is verified</Txt>
        </View>
      </Card>

      {/* Redeem CTA (replaces Buy Credits) */}
      <Card style={{ marginTop: 12 }}>
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          <View style={styles.redeemIcon}>
            <Ionicons name="cash" size={20} color="#7C3AED" />
          </View>
          <View style={{ flex: 1, marginLeft: 10 }}>
            <Txt variant="h3">Redeem Credits</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }} numberOfLines={2}>
              Convert your credits to INR. Minimum {MIN_REDEEM} credits required. Rate: 2 credits = ₹1.
            </Txt>
          </View>
        </View>
        <Button
          testID="redeem-credits-btn"
          title={isEligible ? `Redeem Credits — up to ₹${Math.floor(credits * INR_PER_CREDIT)}` : `Need ${MIN_REDEEM - credits} more credits`}
          disabled={!isEligible}
          onPress={() => router.push("/professional/redeem")}
          icon={<Ionicons name="arrow-forward-circle" size={18} color="#fff" />}
          style={{ marginTop: 12 }}
        />
        {!isEligible ? (
          <Txt variant="small" style={{ color: colors.warning, marginTop: 6 }}>
            Minimum {MIN_REDEEM} credits are required to submit a redemption request.
          </Txt>
        ) : null}
      </Card>

      {/* Redemption history */}
      <TouchableOpacity
        testID="toggle-redemptions"
        onPress={() => setRedemptionsOpen(v => !v)}
        style={styles.historyHeader}
        activeOpacity={0.7}
      >
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          <Ionicons name="document-text" size={18} color={colors.textSecondary} />
          <Txt variant="h3" style={{ marginLeft: 6 }}>Redemption Requests ({reqs.length})</Txt>
        </View>
        <Ionicons name={redemptionsOpen ? "chevron-up" : "chevron-down"} size={22} color={colors.textSecondary} />
      </TouchableOpacity>

      {redemptionsOpen ? (
        <View style={{ marginTop: 8, gap: 8 }}>
          {reqs.length === 0 ? (
            <Txt variant="muted">No redemption requests yet.</Txt>
          ) : null}
          {reqs.map((r) => (
            <Card key={r.id} padding={12}>
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                <View style={{ flex: 1, paddingRight: 8 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", flexWrap: "wrap" }}>
                    <Txt style={{ fontWeight: "700" }}>{r.credits_requested} credits</Txt>
                    <Txt variant="small" style={{ color: colors.textSecondary, marginLeft: 6 }}>
                      → ₹{r.amount_inr?.toFixed(2)}
                    </Txt>
                  </View>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                    {new Date(r.created_at).toLocaleString()}
                  </Txt>
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }} numberOfLines={1}>
                    UPI: {r.upi_id}
                  </Txt>
                  {r.status === "paid" && r.payment_ref ? (
                    <Txt variant="small" style={{ color: colors.success, marginTop: 4 }} numberOfLines={2}>
                      ✅ Ref: {r.payment_ref}{r.payment_date ? ` · ${new Date(r.payment_date).toLocaleDateString()}` : ""}
                    </Txt>
                  ) : null}
                  {r.status === "rejected" && r.rejection_reason ? (
                    <Txt variant="small" style={{ color: colors.error, marginTop: 4 }} numberOfLines={2}>
                      ⚠️ {r.rejection_reason}
                    </Txt>
                  ) : null}
                </View>
                <StatusPill status={r.status} />
              </View>
            </Card>
          ))}
        </View>
      ) : null}

      <TouchableOpacity testID="toggle-history" onPress={() => setHistoryOpen((v) => !v)} style={styles.historyHeader}>
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          <Ionicons name="time" size={18} color={colors.textSecondary} />
          <Txt variant="h3" style={{ marginLeft: 6 }}>Credit History</Txt>
        </View>
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
                  {t.meta?.payment_ref ? (
                    <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }} numberOfLines={1}>
                      Ref: {t.meta.payment_ref}
                    </Txt>
                  ) : null}
                </View>
                <Txt style={{ fontWeight: "800", color: t.delta > 0 ? colors.success : (t.delta < 0 ? colors.error : colors.textSecondary) }}>
                  {t.delta > 0 ? "+" : ""}{t.delta}
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
  hero: { padding: 20, borderRadius: radius.xxl, flexDirection: "row", alignItems: "center", minHeight: 130 },
  heroContent: { flex: 1, minWidth: 0, paddingRight: 8 },
  heroCoin: { width: 80, height: 80, marginLeft: 8 },
  balanceNumber: {
    color: "#fff",
    fontWeight: "900",
    marginTop: 6,
  },
  lockedPill: {
    marginTop: 8, alignSelf: "flex-start",
    flexDirection: "row", alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.25)",
    paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12,
  },
  redeemIcon: { width: 40, height: 40, borderRadius: 12, backgroundColor: "#7C3AED1F", alignItems: "center", justifyContent: "center" },
  historyHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 18, paddingVertical: 10 },
  pill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10, borderWidth: 1, alignSelf: "center" },
});
