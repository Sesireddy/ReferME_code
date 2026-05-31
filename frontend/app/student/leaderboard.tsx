import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Image } from "react-native";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { colors } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { useLocalSearchParams } from "expo-router";

const BADGE = "https://static.prod-images.emergentagent.com/jobs/d2f455eb-160b-40ff-9a4e-1d583c1869b0/images/c7ebd51e366379c5f4ca342b327888d53457f32a01e0c5568f95e97b7d118c69.png";

export default function StudentLeaderboard() {
  const [board, setBoard] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await api<any[]>("/leaderboard/students");
      setBoard(r);
    } catch {}
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const top3 = board.slice(0, 3);
  const rest = board.slice(3);

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <Txt variant="h1">Leaderboard</Txt>
      <Txt variant="muted">Top students by interviews + resume score</Txt>

      <View style={styles.podium}>
        {top3[1] ? <PodiumCol entry={top3[1]} rank={2} height={90} /> : <View style={{ flex: 1 }} />}
        {top3[0] ? <PodiumCol entry={top3[0]} rank={1} height={120} crown /> : <View style={{ flex: 1 }} />}
        {top3[2] ? <PodiumCol entry={top3[2]} rank={3} height={70} /> : <View style={{ flex: 1 }} />}
      </View>

      <View style={{ marginTop: 24, gap: 8 }}>
        {rest.map((e) => (
          <Card key={e.id} padding={14} style={e.is_me ? { borderColor: colors.primary, borderWidth: 2 } : undefined}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <Txt style={{ fontWeight: "800", width: 36, color: colors.textSecondary }}>#{e.rank}</Txt>
              <View style={{ flex: 1 }}>
                <Txt variant="h3">{e.name} {e.is_me ? <Txt style={{ color: colors.primary }}>(you)</Txt> : null}</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>
                  {e.interviews_attended} interviews · resume {e.resume_score}
                </Txt>
              </View>
              <Txt style={{ fontWeight: "800", color: colors.primary }}>{e.score}</Txt>
            </View>
          </Card>
        ))}
      </View>
    </Screen>
  );
}

function PodiumCol({ entry, rank, height, crown }: { entry: any; rank: number; height: number; crown?: boolean }) {
  return (
    <View style={{ flex: 1, alignItems: "center" }}>
      {crown ? <Image source={{ uri: BADGE }} style={{ width: 56, height: 56, marginBottom: -8 }} /> : null}
      <View style={[styles.col, { height, backgroundColor: rank === 1 ? "#FFE4E5" : rank === 2 ? "#F3F4F6" : "#FFF4E0", borderColor: rank === 1 ? colors.primary : colors.border, borderWidth: rank === 1 ? 2 : 1 }]}>
        <Txt style={{ fontWeight: "800", fontSize: 22 }}>#{rank}</Txt>
        <Txt style={{ fontWeight: "700", textAlign: "center", marginTop: 4 }} numberOfLines={1}>{entry.name}</Txt>
        <Txt variant="small" style={{ color: colors.textSecondary }}>{entry.score} pts</Txt>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  podium: { flexDirection: "row", alignItems: "flex-end", justifyContent: "center", gap: 8, marginTop: 16 },
  col: { width: "100%", borderRadius: 16, alignItems: "center", justifyContent: "center", padding: 12 },
});
