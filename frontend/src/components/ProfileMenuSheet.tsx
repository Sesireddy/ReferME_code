import React, { useEffect, useRef } from "react";
import { Modal, View, StyleSheet, TouchableOpacity, Pressable, Animated, Easing } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "./Txt";
import { colors, radius } from "@/src/theme/tokens";

export type MenuItem = {
  key: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  onPress: () => void;
  badge?: string | number;
};

type Props = {
  visible: boolean;
  onClose: () => void;
  items: MenuItem[];
  topOffset?: number;
};

/**
 * Slide-down sheet that anchors below the top-left profile icon.
 * Tapping outside closes it. Tapping an item runs its handler.
 */
export function ProfileMenuSheet({ visible, onClose, items, topOffset = 80 }: Props) {
  const translateY = useRef(new Animated.Value(-20)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      Animated.parallel([
        Animated.timing(translateY, { toValue: 0, duration: 220, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 1, duration: 220, useNativeDriver: true }),
      ]).start();
    } else {
      translateY.setValue(-20);
      opacity.setValue(0);
    }
  }, [visible, translateY, opacity]);

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose} statusBarTranslucent>
      <Pressable testID="menu-backdrop" style={styles.backdrop} onPress={onClose}>
        <Animated.View
          style={[styles.sheet, { top: topOffset, opacity, transform: [{ translateY }] }]}
          // Stop press propagation
          onStartShouldSetResponder={() => true}
        >
          <View style={styles.handle} />
          <View style={{ marginTop: 4 }}>
            {items.map((it) => (
              <TouchableOpacity
                key={it.key}
                testID={`menu-${it.key}`}
                activeOpacity={0.7}
                onPress={() => {
                  onClose();
                  // Small defer so the modal animates out before navigating
                  setTimeout(it.onPress, 50);
                }}
                style={styles.row}
              >
                <View style={[styles.iconWrap, { backgroundColor: it.color + "18" }]}>
                  <Ionicons name={it.icon} size={20} color={it.color} />
                </View>
                <Txt style={styles.label}>{it.label}</Txt>
                {it.badge !== undefined && it.badge !== "" ? (
                  <View style={styles.badge}>
                    <Txt style={styles.badgeText}>{String(it.badge)}</Txt>
                  </View>
                ) : null}
                <Ionicons name="chevron-forward" size={18} color={colors.textSecondary} />
              </TouchableOpacity>
            ))}
          </View>
        </Animated.View>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.35)" },
  sheet: {
    position: "absolute",
    left: 16,
    right: 16,
    backgroundColor: colors.surface,
    borderRadius: radius.xxl,
    paddingVertical: 8,
    paddingHorizontal: 6,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.18,
    shadowRadius: 16,
    elevation: 10,
  },
  handle: { alignSelf: "center", width: 38, height: 4, borderRadius: 2, backgroundColor: colors.border, marginTop: 6, marginBottom: 4 },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 12, paddingHorizontal: 10, borderRadius: radius.lg },
  iconWrap: { width: 36, height: 36, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  label: { flex: 1, marginLeft: 12, fontWeight: "600", fontSize: 15, color: colors.textPrimary },
  badge: { backgroundColor: colors.primary, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, marginRight: 6 },
  badgeText: { color: "#fff", fontSize: 11, fontWeight: "700" },
});
