import React from "react";
import { View, ScrollView, StyleSheet, RefreshControl, KeyboardAvoidingView, Platform } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors } from "@/src/theme/tokens";

/**
 * Global Screen wrapper.
 * Wraps children inside `KeyboardAvoidingView` + a `ScrollView` that automatically
 * scrolls the active input into view when the keyboard opens (keyboardShouldPersistTaps="handled",
 * automaticallyAdjustKeyboardInsets). Ensures fields remain visible across Signup, Login,
 * Profile, Post Job, Slots, and any future forms.
 */
export function Screen({
  children,
  refreshing,
  onRefresh,
  noPad,
}: {
  children: React.ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
  noPad?: boolean;
}) {
  return (
    <SafeAreaView edges={["top"]} style={styles.c}>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={Platform.OS === "ios" ? 0 : 0}
        style={{ flex: 1 }}
      >
        <ScrollView
          contentContainerStyle={{ padding: noPad ? 0 : 20, paddingBottom: 96 }}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive"
          automaticallyAdjustKeyboardInsets
          refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={colors.primary} /> : undefined}
        >
          {children}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({ c: { flex: 1, backgroundColor: colors.bg } });
