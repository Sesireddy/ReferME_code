import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Image, TouchableOpacity, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { ScreenTitle } from "@/src/components/ScreenTitle";
import { Input } from "@/src/components/Input";
import { Picker } from "@/src/components/Picker";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

const BADGE = "https://static.prod-images.emergentagent.com/jobs/d2f455eb-160b-40ff-9a4e-1d583c1869b0/images/c7ebd51e366379c5f4ca342b327888d53457f32a01e0c5568f95e97b7d118c69.png";

const CAT_OPTS = [
  { value: "", label: "All categories" },
  { value: "fresher", label: "Fresher" },
  { value: "experienced", label: "Experienced" },
];

export default function StudentLeaderboard() {
  const [board, setBoard] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  // Filters
  const [category, setCategory] = useState<string | null>("");
  const [skill, setSkill] = useState("");
  const [location, setLocation] = useState("");
  const [minScore, setMinScore] = useState("");
  const [maxScore, setMaxScore] = useState("");
  const [minRating, setMinRating] = useState("");
  const [minJobs, setMinJobs] = useState("");
  const [minRefs, setMinRefs] = useState("");

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      if (skill) params.set("skill", skill);
      if (location) params.set("location", location);
      if (minScore) params.set("min_score", minScore);
      if (maxScore) params.set("max_score", maxScore);
      if (minRating) params.set("min_rating", minRating);
      if (minJobs) params.set("min_jobs_applied", minJobs);
      if (minRefs) params.set("min_referrals", minRefs);
      params.set("page", "1");
      params.set("page_size", "50");
      const qs = params.toString();
      const r = await api<{ items: any[]; total: number } | any[]>(`/leaderboard/students${qs ? "?" + qs : ""}`);
      // Support both legacy array and paginated dict response
      setBoard(Array.isArray(r) ? r : (r.items || []));
    } catch {}
    setRefreshing(false);
  }, [category, skill, location, minScore, maxScore, minRating, minJobs, minRefs]);

  useEffect(() => { load(); }, [load]);

  function clearFilters() {
    setCategory(""); setSkill(""); setLocation("");
    setMinScore(""); setMaxScore("");
    setMinRating(""); setMinJobs(""); setMinRefs("");
  }

  const top3 = board.slice(0, 3);
  const rest = board.slice(3);

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
        <TouchableOpacity testID="filter-btn" onPress={() => setShowFilters((s) => !s)} style={styles.filterBtn}>
          <Ionicons name="options" size={20} color={colors.textPrimary} />
        </TouchableOpacity>
      </View>

      {showFilters ? (
        <Card style={{ marginTop: 12 }}>
          <Picker testID="lb-cat" label="Category" options={CAT_OPTS} value={category} onChange={(v) => setCategory(v as string)} placeholder="All" />
          <Input testID="lb-skill" label="Skill" value={skill} onChangeText={setSkill} placeholder="React, Python" />
          <Input testID="lb-loc" label="Location" value={location} onChangeText={setLocation} placeholder="Bengaluru" />
          <View style={{ flexDirection: "row", gap: 8 }}>
            <View style={{ flex: 1 }}><Input testID="lb-minscore" label="Min score" value={minScore} onChangeText={setMinScore} keyboardType="number-pad" /></View>
            <View style={{ flex: 1 }}><Input testID="lb-maxscore" label="Max score" value={maxScore} onChangeText={setMaxScore} keyboardType="number-pad" /></View>
          </View>
          <Input testID="lb-minrating" label="Min rating" value={minRating} onChangeText={setMinRating} keyboardType="decimal-pad" placeholder="0-5" />
          <View style={{ flexDirection: "row", gap: 8 }}>
            <View style={{ flex: 1 }}><Input testID="lb-minjobs" label="Min jobs applied" value={minJobs} onChangeText={setMinJobs} keyboardType="number-pad" /></View>
            <View style={{ flex: 1 }}><Input testID="lb-minrefs" label="Min referrals" value={minRefs} onChangeText={setMinRefs} keyboardType="number-pad" /></View>
          </View>
          <TouchableOpacity testID="lb-clear" onPress={clearFilters} style={{ alignSelf: "flex-end" }}>
            <Txt style={{ color: colors.primary, fontWeight: "700" }}>Clear filters</Txt>
          </TouchableOpacity>
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
                  <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 2 }}>
                    📍 {e.current_location}
                  </Txt>
                  {e.skills?.length ? (
                    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 6 }}>
                      {e.skills.slice(0, 6).map((s: string) => (
                        <View key={s} style={styles.chip}><Txt variant="small">{s}</Txt></View>
                      ))}
                    </ScrollView>
                  ) : null}
                  <View style={styles.stats}>
                    <Stat label="Score" value={`${e.resume_score}%`} />
                    <Stat label="Interviews" value={e.interviews_attended} />
                    <Stat label="Rating" value={e.rating ? `★ ${e.rating.toFixed(1)}` : "—"} />
                    <Stat label="Applied" value={e.jobs_applied} />
                    <Stat label="Referrals" value={e.referrals_received} />
                  </View>
                </View>
              </View>
            </Card>
          );
        })}
      </View>
      <Txt variant="small" style={{ color: colors.textSecondary, textAlign: "center", marginTop: 16, paddingHorizontal: 20 }}>
        Leaderboard is calculated based on resume score, mock interviews, ratings, and overall platform engagement.
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

function PodiumCol({ entry, rank, height, crown }: { entry: any; rank: number; height: number; crown?: boolean }) {
  return (
    <View style={{ flex: 1, alignItems: "center" }}>
      {crown ? <Image source={{ uri: BADGE }} style={{ width: 56, height: 56, marginBottom: -8 }} /> : null}
      <View style={[styles.col, { height, backgroundColor: rank === 1 ? "#FFE4E5" : rank === 2 ? "#F3F4F6" : "#FFF4E0", borderColor: rank === 1 ? colors.primary : colors.border, borderWidth: rank === 1 ? 2 : 1 }]}>
        <Txt style={{ fontWeight: "800", fontSize: 22 }}>#{rank}</Txt>
        <Txt style={{ fontWeight: "700", textAlign: "center", marginTop: 4 }} numberOfLines={1}>{entry.name}</Txt>
        <Txt variant="small" style={{ color: colors.textSecondary }}>Score {entry.resume_score}</Txt>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  filterBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  podium: { flexDirection: "row", alignItems: "flex-end", justifyContent: "center", gap: 8, marginTop: 16 },
  col: { width: "100%", borderRadius: 16, alignItems: "center", justifyContent: "center", padding: 12 },
  tag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  chip: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, marginRight: 6 },
  stats: { flexDirection: "row", gap: 4, marginTop: 10, backgroundColor: colors.surfaceAlt, borderRadius: 12, padding: 10 },
});
