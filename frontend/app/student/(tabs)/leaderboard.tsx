import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Image, TouchableOpacity, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { ScreenTitle } from "@/src/components/ScreenTitle";
import { Picker } from "@/src/components/Picker";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

const BADGE = "https://static.prod-images.emergentagent.com/jobs/d2f455eb-160b-40ff-9a4e-1d583c1869b0/images/c7ebd51e366379c5f4ca342b327888d53457f32a01e0c5568f95e97b7d118c69.png";

const CAT_OPTS = [
  { value: "", label: "All categories" },
  { value: "fresher", label: "Fresher" },
  { value: "experienced", label: "Experienced" },
];

type LbItem = {
  id: string;
  rank: number;
  name: string;
  category: string;
  skill_set: string;
  current_location: string;
  tps: number;
  resume_score: number;
  interviews_attended: number;
  avg_rating: number;
  is_me?: boolean;
};

export default function StudentLeaderboard() {
  const [board, setBoard] = useState<LbItem[]>([]);
  const [filteredTotal, setFilteredTotal] = useState<number>(0);
  const [baseTotal, setBaseTotal] = useState<number>(0);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true); // initial spinner (also true while filters reload)
  const [showFilters, setShowFilters] = useState(false);

  const [category, setCategory] = useState<string>("");
  const [skill, setSkill] = useState<string>("");
  const [location, setLocation] = useState<string>("");

  const [draftCategory, setDraftCategory] = useState<string>("");
  const [draftSkill, setDraftSkill] = useState<string>("");
  const [draftLocation, setDraftLocation] = useState<string>("");

  const [skillOpts, setSkillOpts] = useState<{ value: string; label: string }[]>([{ value: "", label: "All skills" }]);
  const [locOpts, setLocOpts] = useState<{ value: string; label: string }[]>([{ value: "", label: "All locations" }]);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      if (skill) params.set("skill", skill);
      if (location) params.set("location", location);
      params.set("page", "1");
      params.set("page_size", "100");
      const qs = params.toString();
      const r = await api<{ items: LbItem[]; total: number } | LbItem[]>(`/leaderboard/students${qs ? "?" + qs : ""}`);
      if (Array.isArray(r)) {
        setBoard(r);
        setFilteredTotal(r.length);
      } else {
        setBoard(r.items || []);
        setFilteredTotal(r.total ?? (r.items?.length || 0));
      }
    } catch {}
    setRefreshing(false);
    setLoading(false); // hide initial spinner once first fetch completes
  }, [category, skill, location]);

  useEffect(() => { load(); }, [load]);

  // Fetch the unfiltered global participant count once at mount (used to render
  // "Total participants: N (filtered X: M)" in the header).
  useEffect(() => {
    (async () => {
      try {
        const r = await api<{ total?: number; items?: any[] } | any[]>(`/leaderboard/students?page=1&page_size=1`);
        if (Array.isArray(r)) setBaseTotal(r.length);
        else setBaseTotal(r.total ?? 0);
      } catch {}
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const r = await api<{ skills: string[]; locations: string[] }>("/leaderboard/students/options");
        setSkillOpts([{ value: "", label: "All skills" }, ...(r.skills || []).map((s) => ({ value: s, label: s }))]);
        setLocOpts([{ value: "", label: "All locations" }, ...(r.locations || []).map((l) => ({ value: l, label: l }))]);
      } catch {}
    })();
  }, []);

  function openFilters() {
    setDraftCategory(category);
    setDraftSkill(skill);
    setDraftLocation(location);
    setShowFilters(true);
  }
  function applyFilters() {
    setCategory(draftCategory);
    setSkill(draftSkill);
    setLocation(draftLocation);
    setShowFilters(false);
  }
  function clearFilters() {
    setDraftCategory(""); setDraftSkill(""); setDraftLocation("");
    setCategory(""); setSkill(""); setLocation("");
    setShowFilters(false);
  }

  const hasAppliedFilters = Boolean(category || skill || location);

  // Build the subtitle: two lines. Line 1 shows total participants with the
  // filter-adjusted count in brackets when filters are applied.
  const activeFilters: string[] = [];
  if (category) activeFilters.push(category);
  if (skill) activeFilters.push(skill);
  if (location) activeFilters.push(location);
  const filterLabel = activeFilters.join(", ");
  const line1 = hasAppliedFilters
    ? `Total participants: ${baseTotal} (filtered ${filterLabel}: ${filteredTotal})`
    : `Total participants: ${baseTotal}`;
  const subtitle = `${line1}\nTop 100 performers`;

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <View style={{ flex: 1 }}>
          <ScreenTitle
            title="Leaderboard"
            icon="trophy"
            color={colors.accent}
            subtitle={subtitle}
          />
        </View>
        <TouchableOpacity testID="filter-btn" onPress={openFilters} style={styles.filterBtn}>
          <Ionicons name="options" size={20} color={colors.textPrimary} />
          {hasAppliedFilters ? <View style={styles.filterDot} /> : null}
        </TouchableOpacity>
      </View>

      {showFilters ? (
        <Card style={{ marginTop: 12 }}>
          <Picker testID="lb-cat" label="Category" options={CAT_OPTS} value={draftCategory} onChange={(v) => setDraftCategory(v as string)} placeholder="All categories" />
          <Picker testID="lb-skill" label="Skill" options={skillOpts} value={draftSkill} onChange={(v) => setDraftSkill(v as string)} placeholder="All skills" searchable />
          <Picker testID="lb-loc" label="Location" options={locOpts} value={draftLocation} onChange={(v) => setDraftLocation(v as string)} placeholder="All locations" searchable />
          <View style={styles.filterActions}>
            <TouchableOpacity testID="lb-apply" onPress={applyFilters} style={styles.applyBtn}>
              <Ionicons name="checkmark" size={16} color="#fff" />
              <Txt style={styles.applyBtnText}>Apply Filters</Txt>
            </TouchableOpacity>
            <TouchableOpacity testID="lb-clear" onPress={clearFilters} style={styles.clearBtn}>
              <Txt style={{ color: colors.primary, fontWeight: "700" }}>Clear</Txt>
            </TouchableOpacity>
          </View>
        </Card>
      ) : null}

      {loading ? (
        <View style={styles.loadingWrap} testID="leaderboard-loading">
          <ActivityIndicator size="large" color={colors.primary} />
          <Txt variant="muted" style={{ marginTop: 10 }}>Loading leaderboard…</Txt>
        </View>
      ) : (
        <>
          <View style={styles.podium}>
            {board[1] ? <PodiumCol entry={board[1]} rank={2} height={90} /> : <View style={{ flex: 1 }} />}
            {board[0] ? <PodiumCol entry={board[0]} rank={1} height={120} crown /> : <View style={{ flex: 1 }} />}
            {board[2] ? <PodiumCol entry={board[2]} rank={3} height={70} /> : <View style={{ flex: 1 }} />}
          </View>

          <View style={{ marginTop: 16, gap: 10 }}>
            {board.length === 0 ? <Txt variant="muted">No matches — try adjusting filters.</Txt> : null}
            {board.map((e) => (
              <LeaderRow key={e.id} entry={e} />
            ))}
          </View>
          <Txt variant="small" style={{ color: colors.textSecondary, textAlign: "center", marginTop: 16, paddingHorizontal: 20 }}>
            Ranked by Talent Potential Score (TPS) = 60% Resume + 20% Interviews + 20% Avg Rating.
          </Txt>
        </>
      )}
    </Screen>
  );
}

function LeaderRow({ entry: e }: { entry: LbItem }) {
  const medal = e.rank === 1 ? "🥇" : e.rank === 2 ? "🥈" : e.rank === 3 ? "🥉" : null;
  const topThree = e.rank <= 3;

  // Premium gradient palette per rank
  const rankGradient: [string, string] =
    e.rank === 1 ? ["#FFD700", "#FFA500"] :
    e.rank === 2 ? ["#C0C0C0", "#9CA3AF"] :
    e.rank === 3 ? ["#CD7F32", "#B45309"] :
    ["#FF5A5F", "#FFB347"];

  return (
    <View style={[styles.cardWrap, e.is_me ? styles.cardWrapMe : null]}>
      {/* Premium left rank ribbon */}
      <LinearGradient colors={rankGradient} start={{ x: 0, y: 0 }} end={{ x: 0, y: 1 }} style={styles.rankRibbon}>
        {medal ? <Txt style={{ fontSize: 22 }}>{medal}</Txt> : null}
        <Txt style={[styles.rankNum, { color: topThree ? "#fff" : "#fff" }]}>#{e.rank}</Txt>
      </LinearGradient>

      <View style={styles.cardBody}>
        {/* Header: name + category */}
        <View style={styles.headerRow}>
          <Txt variant="h3" numberOfLines={1} style={{ flexShrink: 1 }}>
            {e.name}
            {e.is_me ? <Txt style={{ color: colors.primary }}> (you)</Txt> : null}
          </Txt>
          {e.category && e.category !== "—" ? (
            <View style={[styles.tag, { backgroundColor: e.category === "experienced" ? "#EDE9FE" : "#E6F9F0" }]}>
              <Txt variant="small" style={{ fontWeight: "700", color: e.category === "experienced" ? "#7C3AED" : colors.success, textTransform: "capitalize" }}>{e.category}</Txt>
            </View>
          ) : null}
        </View>

        {/* Skill + Location row */}
        <View style={styles.metaRow}>
          {e.skill_set && e.skill_set !== "—" ? (
            <View style={styles.metaChip}>
              <Ionicons name="briefcase" size={13} color={colors.professional} />
              <Txt style={styles.metaText} numberOfLines={1}>{e.skill_set}</Txt>
            </View>
          ) : null}
          <View style={styles.metaChip}>
            <Ionicons name="location-sharp" size={13} color={colors.primary} />
            <Txt style={styles.metaText} numberOfLines={1}>{e.current_location}</Txt>
          </View>
        </View>

        {/* TPS hero — full-width gradient */}
        <LinearGradient colors={["#FFF1D6", "#FFE5E7"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.tpsStrip}>
          <View style={styles.tpsIconWrap}>
            <Ionicons name="trophy" size={16} color={colors.accent} />
          </View>
          <Txt style={styles.tpsLabel}>Talent Potential Score</Txt>
          <View style={{ flex: 1 }} />
          <Txt style={styles.tpsValue}>{Math.round(e.tps ?? 0)}</Txt>
          <Txt style={styles.tpsMax}>/100</Txt>
        </LinearGradient>

        {/* Full-width stats row with full labels */}
        <View style={styles.statsRow}>
          <StatBlock
            icon="document-text"
            color="#2563EB"
            bg="#EFF6FF"
            label="Resume Score"
            value={`${e.resume_score}`}
          />
          <StatBlock
            icon="videocam"
            color="#7C3AED"
            bg="#F5F3FF"
            label="Interviews Attended"
            value={String(e.interviews_attended)}
          />
          <StatBlock
            icon="star"
            color="#F59E0B"
            bg="#FFFBEB"
            label="Avg Rating"
            value={e.avg_rating ? e.avg_rating.toFixed(1) : "—"}
          />
        </View>
      </View>
    </View>
  );
}

function StatBlock({ icon, color, bg, label, value }: { icon: any; color: string; bg: string; label: string; value: string }) {
  return (
    <View style={[styles.statBlock, { backgroundColor: bg }]}>
      <View style={styles.statHeader}>
        <Ionicons name={icon} size={13} color={color} />
        <Txt
          style={[styles.statLabel, { color }]}
          numberOfLines={2}
          adjustsFontSizeToFit
          minimumFontScale={0.7}
        >
          {label}
        </Txt>
      </View>
      <Txt
        style={[styles.statValue, { color: colors.textPrimary }]}
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.7}
      >
        {value}
      </Txt>
    </View>
  );
}

function PodiumCol({ entry, rank, height, crown }: { entry: LbItem; rank: number; height: number; crown?: boolean }) {
  const grad: [string, string] =
    rank === 1 ? ["#FFE4E5", "#FFCFD2"] :
    rank === 2 ? ["#F3F4F6", "#E5E7EB"] :
    ["#FFF4E0", "#FFE7B8"];
  return (
    <View style={{ flex: 1, alignItems: "center" }}>
      {crown ? <Image source={{ uri: BADGE }} style={{ width: 56, height: 56, marginBottom: -8 }} /> : null}
      <LinearGradient colors={grad} start={{ x: 0, y: 0 }} end={{ x: 0, y: 1 }} style={[styles.col, { height, borderColor: rank === 1 ? colors.primary : colors.border, borderWidth: rank === 1 ? 2 : 1 }]}>
        <Txt style={{ fontWeight: "800", fontSize: 22 }}>#{rank}</Txt>
        <Txt style={{ fontWeight: "700", textAlign: "center", marginTop: 4 }} numberOfLines={1}>{entry.name}</Txt>
        <Txt variant="small" style={{ color: colors.textSecondary }}>TPS {Math.round(entry.tps ?? 0)}</Txt>
      </LinearGradient>
    </View>
  );
}

const styles = StyleSheet.create({
  filterBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  filterDot: { position: "absolute", top: 8, right: 8, width: 10, height: 10, borderRadius: 5, backgroundColor: colors.primary, borderWidth: 2, borderColor: colors.surface },
  podium: { flexDirection: "row", alignItems: "flex-end", justifyContent: "center", gap: 8, marginTop: 16 },
  col: { width: "100%", borderRadius: 16, alignItems: "center", justifyContent: "center", padding: 12 },

  // Premium row card
  cardWrap: {
    flexDirection: "row",
    backgroundColor: colors.surface,
    borderRadius: 16,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  cardWrapMe: { borderColor: colors.primary, borderWidth: 2 },
  rankRibbon: {
    width: 56,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 14,
    gap: 4,
  },
  rankNum: { fontWeight: "800", fontSize: 16, color: "#fff" },
  cardBody: { flex: 1, padding: 12, gap: 8 },
  headerRow: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  tag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  metaChip: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.surfaceAlt, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8, maxWidth: "60%" },
  metaText: { fontSize: 12, color: colors.textSecondary, fontWeight: "500" },

  // TPS strip
  tpsStrip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 12,
    marginTop: 2,
  },
  tpsIconWrap: { width: 24, height: 24, borderRadius: 12, backgroundColor: "#fff", alignItems: "center", justifyContent: "center" },
  tpsLabel: { fontWeight: "700", color: colors.textPrimary, fontSize: 12 },
  tpsValue: { fontWeight: "800", fontSize: 20, color: colors.primary },
  tpsMax: { fontSize: 12, color: colors.textSecondary, fontWeight: "600" },

  // Stats row
  statsRow: { flexDirection: "row", gap: 6, marginTop: 2 },
  statBlock: { flex: 1, borderRadius: 10, padding: 8, minHeight: 60 },
  statHeader: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: 4 },
  statLabel: { fontSize: 10, fontWeight: "700", flexShrink: 1 },
  statValue: { fontSize: 16, fontWeight: "800" },

  filterActions: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 4 },
  applyBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 12 },
  applyBtnText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  clearBtn: { paddingHorizontal: 14, paddingVertical: 10 },
  loadingWrap: { paddingVertical: 60, alignItems: "center", justifyContent: "center" },
});
