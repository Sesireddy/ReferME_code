import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, Linking, Platform, Share } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { SafeAreaView } from "react-native-safe-area-context";
import * as Clipboard from "expo-clipboard";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { successAlert } from "@/src/lib/successAlert";

type ReferInfo = {
  code: string;
  link: string;
  reward: number;
  total: number;
  successful: number;
  pending: number;
  credits_earned: number;
};

type ReferralRow = {
  id: string;
  status: "pending" | "successful" | "rejected";
  reward_credits: number;
  created_at: string;
  completed_at: string | null;
  name: string;
  email_masked: string;
};

function buildShareMessage(link: string) {
  return [
    "Join ReferME and discover referral jobs, mock interviews, and career opportunities.",
    "",
    "Download using my referral link:",
    link,
    "",
    "Both of us can grow together!",
  ].join("\n");
}

export default function ReferAFriend() {
  const router = useRouter();
  const [info, setInfo] = useState<ReferInfo | null>(null);
  const [list, setList] = useState<ReferralRow[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const me = await api<ReferInfo>("/refer/me");
      setInfo(me);
      const ls = await api<ReferralRow[]>("/refer/list");
      setList(ls || []);
    } catch {}
    setRefreshing(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  async function copy(text: string, label = "Copied!") {
    try {
      await Clipboard.setStringAsync(text);
      successAlert.show({ title: label, message: "Paste it anywhere you like.", intent: "success" });
    } catch {}
  }

  async function nativeShare(message: string) {
    try {
      await Share.share({ message }, { dialogTitle: "Invite a friend to ReferME" });
    } catch {}
  }

  function openSocialShare(channel: string) {
    if (!info) return;
    const msg = buildShareMessage(info.link);
    const enc = encodeURIComponent(msg);
    const link = encodeURIComponent(info.link);
    let url = "";
    switch (channel) {
      case "whatsapp":
        url = `whatsapp://send?text=${enc}`;
        break;
      case "telegram":
        url = `https://t.me/share/url?url=${link}&text=${enc}`;
        break;
      case "facebook":
        url = `https://www.facebook.com/sharer/sharer.php?u=${link}&quote=${enc}`;
        break;
      case "instagram":
        // Instagram has no direct share intent. Copy and prompt the user to paste in IG.
        copy(msg, "Copied for Instagram");
        Linking.openURL("instagram://").catch(() => Linking.openURL("https://www.instagram.com/"));
        return;
      case "gmail":
        url = `mailto:?subject=${encodeURIComponent("Join me on ReferME")}&body=${enc}`;
        break;
      default:
        return nativeShare(msg);
    }
    Linking.openURL(url).catch(async () => {
      // Fallback to OS share sheet if the social app isn't installed
      await nativeShare(msg);
    });
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={["top"]}>
      <View style={styles.header}>
        <TouchableOpacity testID="back-btn" onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="chevron-back" size={28} color={colors.textPrimary} />
        </TouchableOpacity>
        <Txt variant="h3">Refer a Friend</Txt>
        <View style={{ width: 28 }} />
      </View>

      <Screen refreshing={refreshing} onRefresh={load}>
        {/* Hero — gradient reward callout */}
        <LinearGradient colors={["#22C55E", "#16A34A"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.hero}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
            <Ionicons name="gift" size={26} color="#fff" />
            <Txt style={styles.heroTitle}>Earn 25 Credits per signup</Txt>
          </View>
          <Txt style={styles.heroSub}>
            Refer your friends, relatives, and colleagues to ReferME and earn 25 Credits for every successful referral.
          </Txt>
        </LinearGradient>

        {/* Referral link & code */}
        <Card style={{ marginTop: 16 }}>
          <Txt variant="label" style={{ color: colors.textSecondary }}>YOUR REFERRAL CODE</Txt>
          <View style={styles.codeRow}>
            <Txt style={styles.codeText} testID="ref-code" selectable>
              {info?.code || "—"}
            </Txt>
            <TouchableOpacity
              testID="copy-code"
              onPress={() => info && copy(info.code, "Code copied!")}
              style={styles.copyChip}
            >
              <Ionicons name="copy" size={14} color={colors.primary} />
              <Txt style={styles.copyChipText}>Copy</Txt>
            </TouchableOpacity>
          </View>

          <Txt variant="label" style={{ color: colors.textSecondary, marginTop: 10 }}>SHARE LINK</Txt>
          <View style={styles.linkRow}>
            <Txt style={styles.linkText} numberOfLines={1} selectable>{info?.link || "—"}</Txt>
            <TouchableOpacity
              testID="copy-link"
              onPress={() => info && copy(info.link, "Link copied!")}
              style={styles.copyBtn}
            >
              <Ionicons name="copy" size={16} color="#fff" />
            </TouchableOpacity>
          </View>
        </Card>

        {/* Share options grid */}
        <Txt variant="h3" style={{ marginTop: 18, marginBottom: 8 }}>Share via</Txt>
        <View style={styles.shareGrid}>
          <ShareTile testID="share-whatsapp" label="WhatsApp"   icon="logo-whatsapp"   color="#25D366" onPress={() => openSocialShare("whatsapp")} />
          <ShareTile testID="share-telegram" label="Telegram"   icon="paper-plane"     color="#0088CC" onPress={() => openSocialShare("telegram")} />
          <ShareTile testID="share-facebook" label="Facebook"   icon="logo-facebook"   color="#1877F2" onPress={() => openSocialShare("facebook")} />
          <ShareTile testID="share-instagram" label="Instagram" icon="logo-instagram"  color="#E1306C" onPress={() => openSocialShare("instagram")} />
          <ShareTile testID="share-gmail"    label="Gmail"      icon="mail"            color="#EA4335" onPress={() => openSocialShare("gmail")} />
          <ShareTile testID="share-copy"     label="Copy"       icon="link"            color="#6B7280" onPress={() => info && copy(info.link, "Link copied!")} />
          <ShareTile testID="share-native"   label="More"       icon="share-social"    color={colors.primary} onPress={() => info && nativeShare(buildShareMessage(info.link))} />
        </View>

        {/* Tracking stats */}
        <Card style={{ marginTop: 18 }}>
          <Txt variant="h3" style={{ marginBottom: 10 }}>Your referral stats</Txt>
          <View style={styles.statsGrid}>
            <Stat testID="stat-total"      label="Total"          value={info?.total ?? 0}            color="#2563EB" />
            <Stat testID="stat-successful" label="Successful"     value={info?.successful ?? 0}       color={colors.success} />
            <Stat testID="stat-pending"    label="Pending"        value={info?.pending ?? 0}          color={colors.accent} />
            <Stat testID="stat-earned"     label="Credits Earned" value={`${info?.credits_earned ?? 0}`} color={colors.primary} />
          </View>
        </Card>

        {/* Referral list */}
        <Txt variant="h3" style={{ marginTop: 18, marginBottom: 6 }}>Recent referrals</Txt>
        {list.length === 0 ? (
          <Card><Txt variant="muted">No referrals yet. Share your link to start earning!</Txt></Card>
        ) : (
          <View style={{ gap: 8 }}>
            {list.map((r) => (
              <Card key={r.id} padding={12}>
                <View style={{ flexDirection: "row", alignItems: "center" }}>
                  <View style={[styles.avatar, { backgroundColor: badgeBg(r.status) }]}>
                    <Ionicons name="person" size={18} color={badgeFg(r.status)} />
                  </View>
                  <View style={{ flex: 1, marginLeft: 10 }}>
                    <Txt style={{ fontWeight: "700" }} numberOfLines={1}>{r.name}</Txt>
                    <Txt variant="small" style={{ color: colors.textSecondary }} numberOfLines={1}>
                      {r.email_masked} · {new Date(r.created_at).toLocaleDateString()}
                    </Txt>
                  </View>
                  <View style={[styles.statusPill, { backgroundColor: badgeBg(r.status) }]}>
                    <Txt style={{ color: badgeFg(r.status), fontWeight: "700", fontSize: 11, textTransform: "capitalize" }}>
                      {r.status}
                    </Txt>
                  </View>
                </View>
              </Card>
            ))}
          </View>
        )}

        {/* Rules */}
        <Card style={{ marginTop: 18 }}>
          <Txt variant="h3" style={{ marginBottom: 6 }}>How it works</Txt>
          <Bullet>Share your link with friends, relatives, or colleagues.</Bullet>
          <Bullet>They install the app and register a new account.</Bullet>
          <Bullet>Once they verify their email, you earn <Txt style={{ fontWeight: "800" }}>25 Credits</Txt>.</Bullet>
          <Bullet>Same email, phone or account reuse will not be rewarded.</Bullet>
        </Card>
      </Screen>
    </SafeAreaView>
  );
}

function ShareTile({ label, icon, color, onPress, testID }: { label: string; icon: any; color: string; onPress: () => void; testID?: string }) {
  return (
    <TouchableOpacity testID={testID} activeOpacity={0.85} onPress={onPress} style={[styles.shareTile, { borderColor: color + "33" }]}>
      <View style={[styles.shareIcon, { backgroundColor: color + "1A" }]}>
        <Ionicons name={icon} size={22} color={color} />
      </View>
      <Txt style={{ fontSize: 11, fontWeight: "700", color: colors.textPrimary, marginTop: 4 }}>{label}</Txt>
    </TouchableOpacity>
  );
}

function Stat({ label, value, color, testID }: { label: string; value: any; color: string; testID?: string }) {
  return (
    <View testID={testID} style={[styles.statBox, { backgroundColor: color + "12" }]}>
      <Txt style={[styles.statValue, { color }]}>{String(value)}</Txt>
      <Txt style={[styles.statLabel, { color }]} numberOfLines={2} adjustsFontSizeToFit minimumFontScale={0.7}>{label}</Txt>
    </View>
  );
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <View style={{ flexDirection: "row", marginTop: 4 }}>
      <Txt style={{ color: colors.success, marginRight: 6 }}>•</Txt>
      <Txt style={{ flex: 1, color: colors.textPrimary, lineHeight: 20 }}>{children}</Txt>
    </View>
  );
}

function badgeBg(s: string) {
  if (s === "successful") return colors.success + "22";
  if (s === "pending") return colors.accent + "22";
  return colors.error + "22";
}
function badgeFg(s: string) {
  if (s === "successful") return colors.success;
  if (s === "pending") return colors.accent;
  return colors.error;
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border },
  hero: { padding: 18, borderRadius: radius.xxl, gap: 8 },
  heroTitle: { color: "#fff", fontWeight: "800", fontSize: 18, flexShrink: 1 },
  heroSub: { color: "#fff", opacity: 0.95, lineHeight: 20 },
  codeRow: { flexDirection: "row", alignItems: "center", marginTop: 6 },
  codeText: { fontSize: 22, fontWeight: "900", letterSpacing: 1.5, color: colors.primary, flex: 1 },
  copyChip: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, borderWidth: 1, borderColor: colors.primary + "55" },
  copyChipText: { color: colors.primary, fontWeight: "700", fontSize: 12 },
  linkRow: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceAlt, borderRadius: radius.lg, padding: 10, marginTop: 6 },
  linkText: { flex: 1, color: colors.textPrimary, marginRight: 8, fontSize: 13 },
  copyBtn: { width: 34, height: 34, borderRadius: 8, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  shareGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  shareTile: { width: "22.5%", aspectRatio: 1, borderRadius: radius.lg, borderWidth: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  shareIcon: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center" },
  statsGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  statBox: { width: "48%", padding: 12, borderRadius: radius.lg, alignItems: "center" },
  statValue: { fontSize: 26, fontWeight: "900" },
  statLabel: { fontSize: 11, fontWeight: "700", marginTop: 2 },
  avatar: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  statusPill: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 },
});
