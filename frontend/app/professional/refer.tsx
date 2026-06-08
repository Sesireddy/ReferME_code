import React, { useEffect } from "react";
import { View, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { Txt } from "@/src/components/Txt";
import { colors } from "@/src/theme/tokens";

/**
 * The old "Refer Candidate" pool screen has been retired.
 * Per spec, candidate referrals can ONLY happen from the pro's OWN posted jobs.
 * We bounce to /professional/my-jobs which is the new entry point.
 */
export default function ReferRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/professional/my-jobs");
  }, [router]);
  return (
    <View style={styles.center}>
      <Txt variant="muted">Redirecting to My Posted Jobs…</Txt>
    </View>
  );
}
const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg },
});
