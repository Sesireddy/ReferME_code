// Job Seeker — Walk-in & Direct Jobs listing. Shows Admin-posted jobs only. Free access, no Apply CTA.
import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, TouchableOpacity, RefreshControl, FlatList } from "react-native";
import { useRouter, Stack, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";

type Job = {
  id: string;
  title: string;
  company: string;
  location: string;
  experience_min?: number;
  experience_max?: number | null;
  walk_in_date?: string;
  created_at: string;
  employment_type?: string;
  skills_required?: string[];
};

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  } catch { return iso; }
}

export default function WalkinJobsList() {
  const router = useRouter();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const rows = await api<Job[]>("/jobs?source=admin");
      setJobs(rows || []);
    } finally { setBusy(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const renderItem = ({ item: j }: { item: Job }) => {
    const exp = j.experience_min != null || j.experience_max != null
      ? `${j.experience_min ?? 0}${j.experience_max != null ? `-${j.experience_max}` : "+"} yrs`
      : null;
    return (
      <TouchableOpacity testID={`walkin-card-${j.id}`} activeOpacity={0.85} onPress={() => router.push(`/student/walkin-jobs/${j.id}`)}>
        <Card style={{ marginBottom: 12 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
            <View style={{ flex: 1 }}>
              <Txt variant="label" style={{ color: colors.textSecondary }}>{j.company}</Txt>
              <Txt variant="h3" style={{ marginTop: 2 }}>{j.title}</Txt>
            </View>
            <View style={styles.freeBadge}><Ionicons name="gift" size={11} color="#fff" /><Txt style={styles.freeBadgeText}>Free</Txt></View>
          </View>
          <View style={styles.metaRow}>
            <Ionicons name="location" size={13} color={colors.textSecondary} />
            <Txt variant="small" style={styles.metaText}>{j.location}</Txt>
            {exp ? (<><Ionicons name="briefcase" size={13} color={colors.textSecondary} style={{ marginLeft: 10 }} /><Txt variant="small" style={styles.metaText}>{exp}</Txt></>) : null}
          </View>
          {j.walk_in_date ? (
            <View style={styles.metaRow}>
              <Ionicons name="calendar" size={13} color="#F59E0B" />
              <Txt variant="small" style={[styles.metaText, { color: "#F59E0B", fontWeight: "700" }]}>Walk-in: {fmtDate(j.walk_in_date)}</Txt>
            </View>
          ) : null}
          <View style={styles.metaRow}>
            <Ionicons name="time" size={13} color={colors.textSecondary} />
            <Txt variant="small" style={styles.metaText}>Posted {fmtDate(j.created_at)}</Txt>
          </View>
          <Button testID={`walkin-details-${j.id}`} title="Details" style={{ marginTop: 8 }} onPress={() => router.push(`/student/walkin-jobs/${j.id}`)} />
        </Card>
      </TouchableOpacity>
    );
  };

  return (
    <Screen>
      <Stack.Screen options={{ title: "Walk-in & Direct Jobs" }} />
      <FlatList
        data={jobs}
        keyExtractor={(j) => j.id}
        renderItem={renderItem}
        contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={busy} onRefresh={load} />}
        ListEmptyComponent={
          <View style={{ padding: 24, alignItems: "center" }}>
            <Ionicons name="megaphone-outline" size={48} color={colors.textSecondary} />
            <Txt variant="muted" style={{ marginTop: 12, textAlign: "center" }}>
              No Admin-posted opportunities yet. Check back soon for Walk-in Drives, Mass Hiring, and Free Placement events.
            </Txt>
          </View>
        }
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  metaRow: { flexDirection: "row", alignItems: "center", marginTop: 4 },
  metaText: { marginLeft: 4, color: colors.textSecondary },
  freeBadge: { flexDirection: "row", alignItems: "center", backgroundColor: colors.success, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.sm, gap: 3 },
  freeBadgeText: { color: "#fff", fontSize: 11, fontWeight: "800", marginLeft: 3 },
});
