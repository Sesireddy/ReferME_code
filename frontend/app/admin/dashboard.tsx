import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, Modal } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { ConfirmDialog } from "@/src/components/ConfirmDialog";
import { ScreenTitle } from "@/src/components/ScreenTitle";
import { colors } from "@/src/theme/tokens";
import { api, clearSession } from "@/src/lib/api";

type Overview = {
  users: { total: number; students: number; professionals: number; employers: number; active: number; new_today: number };
  jobs: { total: number; active: number; closed: number; posted_today: number };
  applications: { total: number; applied: number; shortlisted: number; referred: number; interview_scheduled: number; hired: number; rejected: number };
  interviews: { slots_total: number; available: number; booked: number; completed: number; cancelled: number };
  credits: { purchased: number; used: number; earned: number; rewarded: number };
  revenue: { total_inr: number; today_inr: number; monthly_inr: number };
};

function StatTile({ label, value, color }: { label: string; value: number | string; color: string }) {
  return (
    <View style={styles.tile}>
      <Txt variant="small" style={{ color: colors.textSecondary, marginBottom: 2 }}>{label}</Txt>
      <Txt variant="h2" style={{ color }}>{value}</Txt>
    </View>
  );
}

function Section({ title, icon, color, children, onSeeAll, seeAllLabel }: { title: string; icon: keyof typeof Ionicons.glyphMap; color: string; children: React.ReactNode; onSeeAll?: () => void; seeAllLabel?: string }) {
  return (
    <Card style={{ marginTop: 16 }}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          <Ionicons name={icon} size={18} color={color} />
          <Txt variant="h3" style={{ marginLeft: 6 }}>{title}</Txt>
        </View>
        {onSeeAll ? (
          <TouchableOpacity onPress={onSeeAll} hitSlop={8}>
            <Txt variant="small" style={{ color: colors.primary, fontWeight: "700" }}>{seeAllLabel || "See all →"}</Txt>
          </TouchableOpacity>
        ) : null}
      </View>
      <View style={styles.tiles}>{children}</View>
    </Card>
  );
}

export default function AdminDashboard() {
  const router = useRouter();
  const [s, setS] = useState<Overview | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [logoutOpen, setLogoutOpen] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const o = await api<Overview>("/admin/stats/overview");
      setS(o);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function confirmLogout() {
    setLogoutOpen(false);
    try { await clearSession(); } catch {}
    router.replace("/");
  }

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={styles.headerRow}>
        <View style={{ flex: 1, paddingRight: 12 }}>
          <ScreenTitle
            title="Admin"
            icon="stats-chart"
            color={colors.admin}
            subtitle="Live platform overview"
          />
        </View>
        <TouchableOpacity
          testID="admin-notif-btn"
          onPress={() => router.push("/notifications")}
          style={[styles.iconBtn, { marginRight: 10 }]}
          activeOpacity={0.7}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <Ionicons name="notifications" size={22} color={colors.textPrimary} />
        </TouchableOpacity>
        <TouchableOpacity
          testID="admin-profile-btn"
          onPress={() => setMenuOpen(true)}
          style={styles.profileBtn}
          activeOpacity={0.7}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <Ionicons name="person-circle" size={32} color="#fff" />
        </TouchableOpacity>
      </View>

      {/* Profile dropdown */}
      <Modal visible={menuOpen} transparent animationType="fade" onRequestClose={() => setMenuOpen(false)}>
        <TouchableOpacity activeOpacity={1} style={styles.menuBg} onPress={() => setMenuOpen(false)}>
          <TouchableOpacity activeOpacity={1} style={styles.menuCard} onPress={() => { /* swallow */ }}>
            <TouchableOpacity testID="menu-profile" style={styles.menuRow} onPress={() => { setMenuOpen(false); }}>
              <Ionicons name="person-circle-outline" size={20} color={colors.primary} />
              <Txt style={styles.menuLabel}>My Profile</Txt>
            </TouchableOpacity>
            <TouchableOpacity testID="menu-settings" style={styles.menuRow} onPress={() => { setMenuOpen(false); }}>
              <Ionicons name="settings-outline" size={20} color="#7C3AED" />
              <Txt style={styles.menuLabel}>Settings</Txt>
            </TouchableOpacity>
            <TouchableOpacity testID="menu-change-password" style={styles.menuRow} onPress={() => { setMenuOpen(false); }}>
              <Ionicons name="key-outline" size={20} color={colors.warning} />
              <Txt style={styles.menuLabel}>Change Password</Txt>
            </TouchableOpacity>
            <TouchableOpacity testID="menu-audit-logs" style={styles.menuRow} onPress={() => { setMenuOpen(false); router.push("/admin/audit-logs"); }}>
              <Ionicons name="time-outline" size={20} color="#2563EB" />
              <Txt style={styles.menuLabel}>Audit Logs</Txt>
            </TouchableOpacity>
            <View style={styles.menuDivider} />
            <TouchableOpacity testID="menu-logout" style={styles.menuRow} onPress={() => { setMenuOpen(false); setLogoutOpen(true); }}>
              <Ionicons name="log-out-outline" size={20} color={colors.error} />
              <Txt style={[styles.menuLabel, { color: colors.error }]}>Logout</Txt>
            </TouchableOpacity>
          </TouchableOpacity>
        </TouchableOpacity>
      </Modal>

      <ConfirmDialog
        visible={logoutOpen}
        title="Are you sure you want to logout?"
        confirmLabel="Yes, Logout"
        cancelLabel="Cancel"
        destructive
        onCancel={() => setLogoutOpen(false)}
        onConfirm={confirmLogout}
      />

      <Section title="User Statistics" icon="people" color={colors.primary} onSeeAll={() => router.push("/admin/users")}>
        <StatTile label="Total Users" value={s?.users.total ?? 0} color={colors.primary} />
        <StatTile label="Job Seekers" value={s?.users.students ?? 0} color="#FF5A5F" />
        <StatTile label="Professionals" value={s?.users.professionals ?? 0} color="#7C3AED" />
        <StatTile label="Employers" value={s?.users.employers ?? 0} color="#2563EB" />
        <StatTile label="Active Users" value={s?.users.active ?? 0} color={colors.success} />
        <StatTile label="New Users Today" value={s?.users.new_today ?? 0} color={colors.warning} />
      </Section>

      <Section title="Job Statistics" icon="briefcase" color="#7C3AED" onSeeAll={() => router.push("/admin/jobs")}>
        <StatTile label="Total Jobs" value={s?.jobs.total ?? 0} color={colors.primary} />
        <StatTile label="Active" value={s?.jobs.active ?? 0} color={colors.success} />
        <StatTile label="Closed" value={s?.jobs.closed ?? 0} color={colors.textSecondary} />
        <StatTile label="Posted Today" value={s?.jobs.posted_today ?? 0} color={colors.warning} />
      </Section>

      <Section title="Application Statistics" icon="document-text" color={colors.accent}>
        <StatTile label="Total" value={s?.applications.total ?? 0} color={colors.primary} />
        <StatTile label="Applied" value={s?.applications.applied ?? 0} color="#2563EB" />
        <StatTile label="Shortlisted" value={s?.applications.shortlisted ?? 0} color={colors.warning} />
        <StatTile label="Referred" value={s?.applications.referred ?? 0} color="#7C3AED" />
        <StatTile label="Interview Sched." value={s?.applications.interview_scheduled ?? 0} color="#FF5A5F" />
        <StatTile label="Hired" value={s?.applications.hired ?? 0} color={colors.success} />
      </Section>

      <Section title="Mock Interview Statistics" icon="videocam" color="#FF5A5F" onSeeAll={() => router.push("/admin/interviews")}>
        <StatTile label="Total Slots" value={s?.interviews.slots_total ?? 0} color={colors.primary} />
        <StatTile label="Available" value={s?.interviews.available ?? 0} color={colors.success} />
        <StatTile label="Booked" value={s?.interviews.booked ?? 0} color={colors.warning} />
        <StatTile label="Completed" value={s?.interviews.completed ?? 0} color="#7C3AED" />
        <StatTile label="Cancelled" value={s?.interviews.cancelled ?? 0} color={colors.error} />
      </Section>

      <Section title="Credit Statistics" icon="card" color={colors.warning} onSeeAll={() => router.push("/admin/transactions")}>
        <StatTile label="Total Purchased" value={s?.credits.purchased ?? 0} color={colors.success} />
        <StatTile label="Total Used" value={s?.credits.used ?? 0} color="#FF5A5F" />
        <StatTile label="Total Earned" value={s?.credits.earned ?? 0} color="#2563EB" />
        <StatTile label="Rewarded" value={s?.credits.rewarded ?? 0} color="#7C3AED" />
      </Section>

      <Section title="Revenue Statistics" icon="cash" color={colors.success}>
        <StatTile label="Total" value={`₹ ${(s?.revenue.total_inr ?? 0).toLocaleString("en-IN")}`} color={colors.success} />
        <StatTile label="Monthly" value={`₹ ${(s?.revenue.monthly_inr ?? 0).toLocaleString("en-IN")}`} color="#7C3AED" />
        <StatTile label="Today" value={`₹ ${(s?.revenue.today_inr ?? 0).toLocaleString("en-IN")}`} color={colors.warning} />
      </Section>

      <View style={{ height: 24 }} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  tiles: { flexDirection: "row", flexWrap: "wrap", marginTop: 12, gap: 12 },
  tile: { width: "47%", backgroundColor: colors.surfaceAlt, borderRadius: 12, padding: 12 },
  iconBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  profileBtn: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: 4,
    paddingBottom: 8,
  },
  menuBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.2)" },
  menuCard: { position: "absolute", top: 60, right: 16, backgroundColor: colors.surface, borderRadius: 14, padding: 6, minWidth: 220, shadowColor: "#000", shadowOpacity: 0.15, shadowRadius: 12, shadowOffset: { width: 0, height: 4 }, elevation: 6 },
  menuRow: { flexDirection: "row", alignItems: "center", paddingHorizontal: 14, paddingVertical: 12, gap: 12 },
  menuLabel: { fontSize: 15, fontWeight: "600", color: colors.textPrimary },
  menuDivider: { height: 1, backgroundColor: colors.border, marginVertical: 4 },
});
