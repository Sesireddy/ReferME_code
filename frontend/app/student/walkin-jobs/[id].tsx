// Job Seeker — Walk-in job details. No Apply button. Free access, full details view.
import React, { useEffect, useState } from "react";
import { View, StyleSheet, ScrollView, Image, TouchableOpacity, Linking, Platform } from "react-native";
import { useLocalSearchParams, Stack } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Clipboard from "expo-clipboard";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { webSafeAlert } from "@/src/lib/webSafeAlert";

type Job = any;

function fmtDate(iso?: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  } catch { return iso; }
}

function Field({ icon, label, value, tint }: { icon: any; label: string; value?: string | null; tint?: string }) {
  if (!value) return null;
  return (
    <View style={styles.field}>
      <View style={[styles.fieldIcon, { backgroundColor: (tint || colors.primary) + "18" }]}>
        <Ionicons name={icon} size={16} color={tint || colors.primary} />
      </View>
      <View style={{ flex: 1 }}>
        <Txt variant="small" style={{ color: colors.textSecondary }}>{label}</Txt>
        <Txt style={{ fontWeight: "600", marginTop: 1 }}>{value}</Txt>
      </View>
    </View>
  );
}

async function copy(value: string, label: string) {
  try {
    await Clipboard.setStringAsync(value);
    webSafeAlert("Copied", `${label} copied to clipboard.`);
  } catch { /* ignore */ }
}

export default function WalkinDetails() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [j, setJ] = useState<Job | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const row = await api<Job>(`/jobs/${id}`);
        setJ(row);
      } catch (e: any) { setErr(e?.message || "Job not found"); }
    })();
  }, [id]);

  if (err) return (
    <Screen><Stack.Screen options={{ title: "Details" }} /><View style={{ padding: 24 }}><Txt variant="muted">{err}</Txt></View></Screen>
  );
  if (!j) return (
    <Screen><Stack.Screen options={{ title: "Details" }} /><View style={{ padding: 24 }}><Txt variant="muted">Loading…</Txt></View></Screen>
  );

  const exp = j.experience_min != null || j.experience_max != null
    ? `${j.experience_min ?? 0}${j.experience_max != null ? `-${j.experience_max}` : "+"} yrs`
    : "";

  return (
    <Screen>
      <Stack.Screen options={{ title: j.company || "Details" }} />
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
        <Card>
          <View style={{ flexDirection: "row", alignItems: "center" }}>
            {j.company_logo_b64 ? (
              <Image source={{ uri: j.company_logo_b64 }} style={{ width: 56, height: 56, borderRadius: 12, marginRight: 12 }} />
            ) : (
              <View style={{ width: 56, height: 56, borderRadius: 12, backgroundColor: colors.primary + "18", alignItems: "center", justifyContent: "center", marginRight: 12 }}>
                <Ionicons name="business" size={26} color={colors.primary} />
              </View>
            )}
            <View style={{ flex: 1 }}>
              <Txt variant="small" style={{ color: colors.textSecondary }}>{j.company}</Txt>
              <Txt variant="h2" style={{ marginTop: 2 }}>{j.title}</Txt>
            </View>
            <View style={styles.freeBadge}><Ionicons name="gift" size={11} color="#fff" /><Txt style={styles.freeBadgeText}>Free</Txt></View>
          </View>
        </Card>

        <Card style={{ marginTop: 12 }}>
          <Txt variant="h3" style={{ marginBottom: 8 }}>Overview</Txt>
          <Field icon="location" label="Location" value={j.location} tint="#2563EB" />
          <Field icon="briefcase" label="Experience" value={exp || undefined} tint="#7C3AED" />
          <Field icon="people" label="Open Positions" value={j.open_positions ? String(j.open_positions) : undefined} tint="#F59E0B" />
          <Field icon="business" label="Employment Type" value={j.employment_type} tint="#10B981" />
          <Field icon="cash" label="Salary" value={j.salary_range || undefined} tint="#059669" />
        </Card>

        {j.description ? (
          <Card style={{ marginTop: 12 }}>
            <Txt variant="h3" style={{ marginBottom: 6 }}>Job Description</Txt>
            <Txt style={{ lineHeight: 22 }}>{j.description}</Txt>
          </Card>
        ) : null}

        {j.skills_required?.length ? (
          <Card style={{ marginTop: 12 }}>
            <Txt variant="h3" style={{ marginBottom: 8 }}>Required Skills</Txt>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
              {j.skills_required.map((s: string) => (
                <View key={s} style={styles.skillChip}><Txt style={{ color: colors.primary, fontWeight: "700", fontSize: 12 }}>{s}</Txt></View>
              ))}
            </View>
          </Card>
        ) : null}

        {(j.walk_in_date || j.walk_in_time || j.venue) ? (
          <Card style={{ marginTop: 12 }}>
            <Txt variant="h3" style={{ marginBottom: 8 }}>Walk-in Details</Txt>
            <Field icon="calendar" label="Walk-in Date" value={fmtDate(j.walk_in_date)} tint="#F59E0B" />
            <Field icon="time" label="Walk-in Time" value={j.walk_in_time} tint="#F59E0B" />
            <Field icon="location" label="Venue" value={j.venue} tint="#2563EB" />
          </Card>
        ) : null}

        {(j.contact_person || j.contact_number || j.contact_email) ? (
          <Card style={{ marginTop: 12 }}>
            <Txt variant="h3" style={{ marginBottom: 8 }}>Contact</Txt>
            <Field icon="person" label="Contact Person" value={j.contact_person} tint="#7C3AED" />
            {j.contact_number ? (
              <TouchableOpacity testID="contact-call" onPress={() => Platform.OS === "web" ? copy(j.contact_number, "Contact Number") : Linking.openURL(`tel:${j.contact_number}`)}>
                <Field icon="call" label="Contact Number (tap to copy/call)" value={j.contact_number} tint="#10B981" />
              </TouchableOpacity>
            ) : null}
            {j.contact_email ? (
              <TouchableOpacity testID="contact-email" onPress={() => Platform.OS === "web" ? copy(j.contact_email, "Contact Email") : Linking.openURL(`mailto:${j.contact_email}`)}>
                <Field icon="mail" label="Contact Email (tap to copy/email)" value={j.contact_email} tint="#EF4444" />
              </TouchableOpacity>
            ) : null}
            {j.application_deadline ? <Field icon="hourglass" label="Application Deadline" value={fmtDate(j.application_deadline)} tint="#EF4444" /> : null}
          </Card>
        ) : null}

        <View style={styles.noApplyBanner}>
          <Ionicons name="information-circle" size={16} color={colors.textSecondary} />
          <Txt variant="small" style={{ color: colors.textSecondary, marginLeft: 6, flex: 1 }}>
            Admin-posted opening — no Apply button, no credits. Use the contact details above to reach out directly.
          </Txt>
        </View>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  field: { flexDirection: "row", alignItems: "center", marginBottom: 10 },
  fieldIcon: { width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center", marginRight: 10 },
  skillChip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: colors.primary + "12", borderWidth: 1, borderColor: colors.primary + "33" },
  freeBadge: { flexDirection: "row", alignItems: "center", backgroundColor: colors.success, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.sm },
  freeBadgeText: { color: "#fff", fontSize: 11, fontWeight: "800", marginLeft: 3 },
  noApplyBanner: { flexDirection: "row", alignItems: "flex-start", marginTop: 16, padding: 12, backgroundColor: colors.surfaceAlt, borderRadius: radius.lg },
});
