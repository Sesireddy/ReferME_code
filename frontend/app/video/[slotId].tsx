import React, { useEffect, useState } from "react";
import { View, StyleSheet, ActivityIndicator, Platform, TouchableOpacity, Alert } from "react-native";
import { useLocalSearchParams, useRouter, Stack } from "expo-router";
import { WebView } from "react-native-webview";
import { Ionicons } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import * as WebBrowser from "expo-web-browser";
import { Txt } from "@/src/components/Txt";
import { Button } from "@/src/components/Button";
import { colors } from "@/src/theme/tokens";
import { api, getUser } from "@/src/lib/api";

/**
 * In-app video interview screen powered by Jitsi Meet (https://meet.jit.si).
 * - The slot's meeting_url is loaded inside a WebView.
 * - Mic & camera permissions must be granted by the user via the WebView prompt.
 * - If WebView fails or runs on web, falls back to opening in the system browser.
 */
export default function VideoCallScreen() {
  const { slotId } = useLocalSearchParams<{ slotId: string }>();
  const router = useRouter();
  const [slot, setSlot] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
    (async () => {
      try {
        const u = await getUser();
        setUser(u);
        const list = await api<any[]>("/interviews/my-bookings");
        const found = list.find((x) => x.id === slotId);
        if (!found) {
          setErr("Session not found or you don't have access to it.");
        } else {
          setSlot(found);
        }
      } catch (e: any) {
        setErr(e.message || "Failed to load session.");
      } finally {
        setLoading(false);
      }
    })();
  }, [slotId]);

  async function openExternal() {
    if (!slot?.meeting_url) return;
    try {
      await WebBrowser.openBrowserAsync(slot.meeting_url);
    } catch (e: any) {
      Alert.alert("Could not open meeting", e.message || String(e));
    }
  }

  if (loading) {
    return (
      <SafeAreaView style={styles.fullCenter} edges={["top", "bottom"]}>
        <Stack.Screen options={{ headerShown: false }} />
        <ActivityIndicator size="large" color={colors.primary} />
        <Txt variant="muted" style={{ marginTop: 12 }}>Loading session…</Txt>
      </SafeAreaView>
    );
  }

  if (err || !slot) {
    return (
      <SafeAreaView style={styles.fullCenter} edges={["top", "bottom"]}>
        <Stack.Screen options={{ headerShown: false }} />
        <Ionicons name="alert-circle" size={48} color={colors.primary} />
        <Txt variant="h3" style={{ marginTop: 12, textAlign: "center" }}>{err || "Session not found"}</Txt>
        <Button title="Go back" onPress={() => router.back()} style={{ marginTop: 20, paddingHorizontal: 32 }} />
      </SafeAreaView>
    );
  }

  const url = slot.meeting_url as string;
  const userName = user?.name || (user?.email || "Guest").split("@")[0];

  // Build URL with config params to skip pre-join screen and inject display name.
  const u = new URL(url);
  // Hash params for Jitsi config — non-encoded, # delimits config.
  const cfg = [
    `userInfo.displayName="${encodeURIComponent(userName)}"`,
    `config.prejoinPageEnabled=false`,
    `config.disableDeepLinking=true`,
    `config.startWithAudioMuted=false`,
    `config.startWithVideoMuted=false`,
  ].join("&");
  const finalUrl = `${u.toString()}#${cfg}`;

  // Web fallback: open in new tab (WebView on web is unreliable)
  if (Platform.OS === "web") {
    return (
      <SafeAreaView style={styles.fullCenter} edges={["top", "bottom"]}>
        <Stack.Screen options={{ headerShown: false }} />
        <Ionicons name="videocam" size={48} color={colors.primary} />
        <Txt variant="h2" style={{ marginTop: 12 }}>Ready to join</Txt>
        <Txt variant="muted" style={{ marginTop: 6, textAlign: "center" }}>
          With {slot.counterparty_name || "your partner"}
        </Txt>
        <Button title="Open Video Room" onPress={openExternal} style={{ marginTop: 24, paddingHorizontal: 36 }} />
        <TouchableOpacity onPress={() => router.back()} style={{ marginTop: 14 }}>
          <Txt variant="muted">Cancel</Txt>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: "#000" }}>
      <Stack.Screen options={{ headerShown: false }} />
      <SafeAreaView edges={["top"]} style={styles.headerBar}>
        <TouchableOpacity testID="vc-close" onPress={() => router.back()} style={styles.closeBtn}>
          <Ionicons name="chevron-back" size={26} color="#fff" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Txt style={{ color: "#fff", fontWeight: "700" }}>{slot.counterparty_name || "Mock Interview"}</Txt>
          <Txt style={{ color: "rgba(255,255,255,0.7)", fontSize: 12 }}>
            {(slot.skill_set || []).join(", ") || slot.topic || "Live session"}
          </Txt>
        </View>
        <TouchableOpacity onPress={openExternal} style={styles.closeBtn}>
          <Ionicons name="open-outline" size={22} color="#fff" />
        </TouchableOpacity>
      </SafeAreaView>
      <WebView
        source={{ uri: finalUrl }}
        style={{ flex: 1, backgroundColor: "#000" }}
        originWhitelist={["*"]}
        javaScriptEnabled
        domStorageEnabled
        mediaPlaybackRequiresUserAction={false}
        allowsInlineMediaPlayback
        allowsFullscreenVideo
        startInLoadingState
        renderLoading={() => (
          <View style={styles.fullCenter}>
            <ActivityIndicator size="large" color="#fff" />
            <Txt style={{ color: "#fff", marginTop: 12 }}>Connecting to Jitsi…</Txt>
          </View>
        )}
        onError={(e) => {
          const msg = e.nativeEvent?.description || "WebView error";
          Alert.alert("Connection issue", `${msg}\nWe'll open it in your browser instead.`, [
            { text: "OK", onPress: openExternal },
          ]);
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  fullCenter: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg, padding: 24 },
  headerBar: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingVertical: 8, backgroundColor: "#000" },
  closeBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
});
