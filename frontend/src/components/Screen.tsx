import React from "react";
import { View, ScrollView, StyleSheet, RefreshControl } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors } from "@/src/theme/tokens";

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
      <ScrollView
        contentContainerStyle={{ padding: noPad ? 0 : 20, paddingBottom: 32 }}
        refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={colors.primary} /> : undefined}
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({ c: { flex: 1, backgroundColor: colors.bg } });
