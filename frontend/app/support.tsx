import React, { useState } from "react";
import { View, StyleSheet, TouchableOpacity, Alert, ScrollView, Platform, KeyboardAvoidingView } from "react-native";
import * as DocumentPicker from "expo-document-picker";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { ScreenTitle } from "@/src/components/ScreenTitle";
import { colors, radius } from "@/src/theme/tokens";
import { api } from "@/src/lib/api";
import { fileToDataUri } from "@/src/lib/fileToDataUri";

/**
 * Support screen (Iteration 62) — replaces the old broken "Raise a Dispute" flow that
 * incorrectly redirected users to Notifications.
 *
 * Spec:
 *   - Subject (Mandatory), Issue Description (Mandatory), Attachment (Optional)
 *   - Submit + Cancel buttons
 *   - On success: centered single-OK popup + navigate back
 *   - Backend POST /api/support/tickets creates a ticket + emails support@refermejobs.com
 *   - Applies to all roles (Job Seeker, Working Professional, Admin)
 */
export default function Support() {
  const router = useRouter();
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [attachmentUri, setAttachmentUri] = useState<string>("");
  const [attachmentName, setAttachmentName] = useState<string>("");
  const [attachmentMime, setAttachmentMime] = useState<string>("");
  const [busy, setBusy] = useState(false);

  async function pickAttachment() {
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: ["image/*", "application/pdf"],
        copyToCacheDirectory: true,
      });
      if (res.canceled || !res.assets?.[0]) return;
      const a = res.assets[0];
      const mime = a.mimeType || (a.name?.endsWith(".pdf") ? "application/pdf" : "image/jpeg");
      const dataUri = await fileToDataUri(a.uri, { forceMime: mime });
      setAttachmentUri(dataUri);
      setAttachmentName(a.name || "attachment");
      setAttachmentMime(mime);
    } catch (e: any) {
      Alert.alert("Attachment failed", String(e?.message || e));
    }
  }

  function clearAttachment() {
    setAttachmentUri("");
    setAttachmentName("");
    setAttachmentMime("");
  }

  async function submit() {
    const s = subject.trim();
    const d = description.trim();
    if (s.length < 3) {
      Alert.alert("Subject required", "Please enter a subject (at least 3 characters).");
      return;
    }
    if (d.length < 5) {
      Alert.alert("Description required", "Please describe your issue (at least 5 characters).");
      return;
    }
    setBusy(true);
    try {
      await api<{ message: string; ticket_id: string }>("/support/tickets", {
        method: "POST",
        body: {
          subject: s,
          description: d,
          attachment_base64: attachmentUri || undefined,
          attachment_filename: attachmentName || undefined,
          attachment_mime: attachmentMime || undefined,
        },
      });
      Alert.alert(
        "Issue Submitted Successfully",
        "Thank you for contacting the ReferME Support Team.\n\nYour issue has been submitted successfully. Our support team will review your request and contact you shortly.",
        [{ text: "OK", onPress: () => router.back() }],
      );
    } catch (e: any) {
      Alert.alert("Could not submit", e?.message || "Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 48 }} keyboardShouldPersistTaps="handled">
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <TouchableOpacity
              testID="support-back"
              onPress={() => router.back()}
              hitSlop={10}
              style={styles.backBtn}
            >
              <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
            </TouchableOpacity>
            <View style={{ flex: 1 }}>
              <ScreenTitle title="Raise an Issue" color={colors.primary} subtitle="Our support team is here to help." />
            </View>
          </View>

          <Card style={{ marginTop: 12 }}>
            <Input
              testID="support-subject"
              label="Subject *"
              value={subject}
              onChangeText={setSubject}
              placeholder="e.g. Payment not credited"
              maxLength={120}
            />
            <Input
              testID="support-description"
              label="Issue Description *"
              value={description}
              onChangeText={setDescription}
              placeholder="Please describe your issue in detail…"
              multiline
              numberOfLines={6}
              style={{ minHeight: 140, textAlignVertical: "top" }}
            />
            <Txt variant="label" style={{ marginTop: 12 }}>Attachment / Screenshot (Optional)</Txt>
            {attachmentUri ? (
              <View style={styles.attachRow} testID="support-attach-row">
                <Ionicons name={attachmentMime === "application/pdf" ? "document-text" : "image"} size={20} color={colors.primary} />
                <Txt variant="small" style={{ flex: 1, marginLeft: 8 }} numberOfLines={1}>{attachmentName}</Txt>
                <TouchableOpacity testID="support-attach-remove" onPress={clearAttachment} hitSlop={10}>
                  <Ionicons name="close-circle" size={22} color={colors.error} />
                </TouchableOpacity>
              </View>
            ) : (
              <TouchableOpacity testID="support-attach-add" onPress={pickAttachment} style={styles.attachAdd}>
                <Ionicons name="attach" size={18} color={colors.primary} />
                <Txt style={{ marginLeft: 6, color: colors.primary, fontWeight: "700" }}>Add screenshot or PDF</Txt>
              </TouchableOpacity>
            )}

            <View style={{ flexDirection: "row", gap: 12, marginTop: 20 }}>
              <Button testID="support-cancel" title="Cancel" variant="outline" onPress={() => router.back()} style={{ flex: 1 }} />
              <Button testID="support-submit" title="Submit" onPress={submit} loading={busy} style={{ flex: 1 }} />
            </View>
          </Card>

          <Card style={{ marginTop: 16 }}>
            <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 6 }}>
              <Ionicons name="help-circle" size={20} color={colors.accent} />
              <Txt variant="h3" style={{ marginLeft: 8 }}>Need help?</Txt>
            </View>
            <Txt variant="small" style={{ color: colors.textSecondary, lineHeight: 20 }}>
              For any technical issues, payment queries, account-related concerns, or general assistance, please contact us at:
            </Txt>
            <Txt style={{ marginTop: 8, color: colors.primary, fontWeight: "700" }} selectable>
              support@refermejobs.com
            </Txt>
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  backBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  attachRow: {
    flexDirection: "row",
    alignItems: "center",
    padding: 10,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceAlt,
    marginTop: 6,
  },
  attachAdd: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 12,
    marginTop: 6,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: colors.primary + "88",
    backgroundColor: colors.primary + "10",
  },
});
