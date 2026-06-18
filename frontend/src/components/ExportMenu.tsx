import React, { useState } from "react";
import { View, StyleSheet, TouchableOpacity, Modal, Alert, Platform } from "react-native";
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "./Txt";
import { colors } from "@/src/theme/tokens";

type Props = {
  /** entity slug: 'users' | 'jobs' | 'interviews' | 'transactions' | 'redemptions' */
  entity: "users" | "jobs" | "interviews" | "transactions" | "redemptions";
  /** Display label for the menu button (e.g. "Export Users") */
  label?: string;
  iconColor?: string;
};

/**
 * ExportMenu — a single round button that opens a popup with CSV / PDF download options.
 * Drops in to any admin screen header.
 */
export function ExportMenu({ entity, label, iconColor }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const downloadOnWeb = (url: string, filename: string) => {
    // For web: trigger a real browser download using a link
    if (typeof document !== "undefined") {
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.target = "_blank";
      document.body.appendChild(a);
      a.click();
      a.remove();
      return true;
    }
    return false;
  };

  async function exportAs(fmt: "csv" | "pdf") {
    if (busy) return;
    setBusy(true);
    setOpen(false);
    try {
      const base = process.env.EXPO_PUBLIC_BACKEND_URL || "";
      // Reuse the same token from AsyncStorage (api.ts handles it but for direct GET we attach manually)
      const tokenMod = await import("@/src/lib/api");
      const token = await (tokenMod as any).getToken?.();
      const url = `${base}/api/admin/export/${entity}?fmt=${fmt}`;
      const filename = `referme_${entity}_${Date.now()}.${fmt}`;

      if (Platform.OS === "web") {
        // Web: open authenticated URL via fetch+blob (since we need Auth header)
        const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
        if (!r.ok) throw new Error(`Export failed (${r.status})`);
        const blob = await r.blob();
        const objectUrl = URL.createObjectURL(blob);
        downloadOnWeb(objectUrl, filename);
        setTimeout(() => URL.revokeObjectURL(objectUrl), 5000);
      } else {
        // Native: download to cache then share
        const dest = (FileSystem.cacheDirectory || "") + filename;
        const dl = await FileSystem.downloadAsync(url, dest, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (await Sharing.isAvailableAsync()) {
          await Sharing.shareAsync(dl.uri, {
            mimeType: fmt === "pdf" ? "application/pdf" : "text/csv",
            dialogTitle: `Export ${entity}`,
            UTI: fmt === "pdf" ? "com.adobe.pdf" : "public.comma-separated-values-text",
          });
        } else {
          Alert.alert("Saved", `File saved to ${dl.uri}`);
        }
      }
    } catch (e: any) {
      Alert.alert("Export failed", e?.message || "Could not export. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const c = iconColor || colors.primary;

  return (
    <>
      <TouchableOpacity
        testID={`export-${entity}-btn`}
        onPress={() => setOpen(true)}
        style={styles.btn}
        activeOpacity={0.7}
        hitSlop={10}
      >
        <Ionicons name="download-outline" size={20} color={c} />
      </TouchableOpacity>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <TouchableOpacity activeOpacity={1} style={styles.bg} onPress={() => setOpen(false)}>
          <View style={styles.card} onStartShouldSetResponder={() => true}>
            <Txt variant="h3" style={{ textAlign: "center" }}>{label || `Export ${entity}`}</Txt>
            <Txt variant="small" style={{ textAlign: "center", color: colors.textSecondary, marginTop: 4, marginBottom: 14 }}>
              Choose a format to download
            </Txt>
            <TouchableOpacity testID={`export-${entity}-csv`} style={styles.opt} onPress={() => exportAs("csv")}>
              <Ionicons name="document-text" size={22} color="#10B981" />
              <View style={{ marginLeft: 12, flex: 1 }}>
                <Txt style={{ fontWeight: "700" }}>CSV (Spreadsheet)</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>Open in Excel / Google Sheets</Txt>
              </View>
            </TouchableOpacity>
            <TouchableOpacity testID={`export-${entity}-pdf`} style={styles.opt} onPress={() => exportAs("pdf")}>
              <Ionicons name="document" size={22} color="#EF4444" />
              <View style={{ marginLeft: 12, flex: 1 }}>
                <Txt style={{ fontWeight: "700" }}>PDF Document</Txt>
                <Txt variant="small" style={{ color: colors.textSecondary }}>Printable, shareable report</Txt>
              </View>
            </TouchableOpacity>
          </View>
        </TouchableOpacity>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  btn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", alignItems: "center", justifyContent: "center", paddingHorizontal: 32 },
  card: { width: "100%", maxWidth: 360, backgroundColor: colors.surface, borderRadius: 18, padding: 16 },
  opt: { flexDirection: "row", alignItems: "center", padding: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, marginTop: 8 },
});
