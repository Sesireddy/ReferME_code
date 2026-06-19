import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Image, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
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
  const [refreshing, setRefreshing] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  // Applied filters (drive the network query)
  const [category, setCategory] = useState<string>("");
  const [skill, setSkill] = useState<string>("");
  const [location, setLocation] = useState<string>("");

  // Draft filters (only inside the popup, until "Apply Filters" is pressed)
  const [draftCategory, setDraftCategory] = useState<string>("");
  const [draftSkill, setDraftSkill] = useState<string>("");
  const [draftLocation, setDraftLocation] = useState<string>("");

  // Dropdown options fetched from backend
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
      setBoard(Array.isArray(r) ? r : (r.items || []));
    } catch {}
    setRefreshing(false);
  }, [category, skill, location]);

  useEffect(() => { load(); }, [load]);

  // Load dropdown options once
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
    // Sync drafts with the currently-applied filters before opening
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
    setDraftCategory("");
    setDraftSkill("");
    setDraftLocation("");
    setCategory("");
    setSkill("");
    setLocation("");
    setShowFilters(false);
  }

  const hasAppliedFilters = Boolean(category || skill || location);

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <View style={{ flex: 1 }}>
          <ScreenTitle
            title="Leaderboard"
            icon="trophy"
            color={colors.accent}
            subtitle={`Top performers · ${board.length} participants`}
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

      <View style={styles.podium}>
        {board[1] ? <PodiumCol entry={board[1]} rank={2} height={90} /> : <View style={{ flex: 1 }} />}
        {board[0] ? <PodiumCol entry={board[0]} rank={1} height={120} crown /> : <View style={{ flex: 1 }} />}
        {board[2] ? <PodiumCol entry={board[2]} rank={3} height={70} /> : <View style={{ flex: 1 }} />}
      </View>

      <View style={{ marginTop: 16, gap: 8 }}>
        {board.length === 0 ? <Txt variant="muted">No matches — try adjusting filters.</Txt> : null}
        {board.map((e) => {
          const medal = e.rank === 1 ? "🥇" : e.rank === 2 ? "🥈" : e.rank === 3 ? "🥉" : null;
          return (
            <Card key={e.id} padding={14} style={e.is_me ? { borderColor: colors.primary, borderWidth: 2 } : undefined}>
              <View style={{ flexDirection: "row", alignItems: "flex-start" }}>
                <View style={{ width: 44, alignItems: "center" }}>
                  {medal ? <Txt style={{ fontSize: 24 }}>{medal}</Txt> : null}
                  <Txt style={{ fontWeight: "800", color: colors.textSecondary, fontSize: 16, marginTop: medal ? 2 : 0 }}>#{e.rank}</Txt>
                </View>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <Txt variant="h3">{e.name}{e.is_me ? <Txt style={{ color: colors.primary }}> (you)</Txt> : null}</Txt>
                    {e.category && e.category !== "—" ? (
                      <View style={[styles.tag, { backgroundColor: e.category === "experienced" ? "#EDE9FE" : "#E6F9F0" }]}>
                        <Txt variant="small" style={{ fontWeight: "700", color: e.category === "experienced" ? "#7C3AED" : colors.success, textTransform: "capitalize" }}>{e.category}</Txt>
                      </View>
                    ) : null}
                  </View>
                  <View style={{ flexDirection: "row", gap: 12, marginTop: 4, flexWrap: "wrap" }}>
                    {e.skill_set && e.skill_set !== "—" ? (
                      <Txt variant="small" style={{ color: colors.textSecondary }}>🧠 {e.skill_set}</Txt>
                    ) : null}
                    <Txt variant="small" style={{ color: colors.textSecondary }}>📍 {e.current_location}</Txt>
                  </View>

                  {/* TPS hero strip */}
                  <View style={styles.tpsRow}>
                    <Ionicons name="trophy" size={14} color={colors.accent} />
                    <Txt style={styles.tpsLabel}>TPS</Txt>
                    <Txt style={styles.tpsValue}>{e.tps?.toFixed(2) ?? "0.00"}</Txt>
                    <Txt style={styles.tpsMax}>/100</Txt>
                  </View>

                  <View style={styles.stats}>
                    <Stat label="Resume" value={`${e.resume_score}`} />
                    <Stat label="Interviews" value={e.interviews_attended} />
                    <Stat label="Avg Rating" value={e.avg_rating ? `★ ${e.avg_rating.toFixed(1)}` : "—"} />
                  </View>
                </View>
              </View>
            </Card>
          );
        })}
      </View>
      <Txt variant="small" style={{ color: colors.textSecondary, textAlign: "center", marginTop: 16, paddingHorizontal: 20 }}>
        Ranked by Talent Potential Score (TPS) = 60% Resume + 20% Interviews + 20% Avg Rating.
      </Txt>
    </Screen>
  );
}

function Stat({ label, value }: { label: string; value: any }) {
  return (
    <View style={{ alignItems: "center", flex: 1, paddingHorizontal: 2 }}>
      <Txt
        variant="small"
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.7}
        style={{ color: colors.textSecondary, fontSize: 11, textAlign: "center" }}
      >
        {label}
      </Txt>
      <Txt
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.7}
        style={{ fontWeight: "700", marginTop: 2, fontSize: 13, textAlign: "center" }}
      >
        {String(value)}
      </Txt>
    </View>
  );
}

function PodiumCol({ entry, rank, height, crown }: { entry: LbItem; rank: number; height: number; crown?: boolean }) {
  return (
    <View style={{ flex: 1, alignItems: "center" }}>
      {crown ? <Image source={{ uri: BADGE }} style={{ width: 56, height: 56, marginBottom: -8 }} /> : null}
      <View style={[styles.col, { height, backgroundColor: rank === 1 ? "#FFE4E5" : rank === 2 ? "#F3F4F6" : "#FFF4E0", borderColor: rank === 1 ? colors.primary : colors.border, borderWidth: rank === 1 ? 2 : 1 }]}>
        <Txt style={{ fontWeight: "800", fontSize: 22 }}>#{rank}</Txt>
        <Txt style={{ fontWeight: "700", textAlign: "center", marginTop: 4 }} numberOfLines={1}>{entry.name}</Txt>
        <Txt variant="small" style={{ color: colors.textSecondary }}>TPS {entry.tps?.toFixed(1) ?? "0"}</Txt>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  filterBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  filterDot: { position: "absolute", top: 8, right: 8, width: 10, height: 10, borderRadius: 5, backgroundColor: colors.primary, borderWidth: 2, borderColor: colors.surface },
  podium: { flexDirection: "row", alignItems: "flex-end", justifyContent: "center", gap: 8, marginTop: 16 },
  col: { width: "100%", borderRadius: 16, alignItems: "center", justifyContent: "center", padding: 12 },
  tag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  chip: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, marginRight: 6 },
  stats: { flexDirection: "row", gap: 4, marginTop: 10, backgroundColor: colors.surfaceAlt, borderRadius: 12, padding: 10 },
  tpsRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 8, paddingVertical: 6, paddingHorizontal: 10, backgroundColor: "#FFF7E6", borderRadius: 10, alignSelf: "flex-start" },
  tpsLabel: { fontWeight: "700", color: colors.accent, fontSize: 12 },
  tpsValue: { fontWeight: "800", fontSize: 16, color: colors.textPrimary },
  tpsMax: { fontSize: 12, color: colors.textSecondary },
  filterActions: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 4 },
  applyBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 12 },
  applyBtnText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  clearBtn: { paddingHorizontal: 14, paddingVertical: 10 },
});
