import React, { useEffect, useState, useCallback } from "react";
import { View, StyleSheet, Alert, TouchableOpacity, Modal, Image } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { Input } from "@/src/components/Input";
import { colors, radius } from "@/src/theme/tokens";
import { api, clearSession } from "@/src/lib/api";

export default function ProProfile() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [profile, setProfile] = useState<any>({});
  const [completion, setCompletion] = useState<number>(0);
  const [refreshing, setRefreshing] = useState(false);

  // editable
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [company, setCompany] = useState("");
  const [designation, setDesignation] = useState("");
  const [years, setYears] = useState("");
  const [location, setLocation] = useState("");
  const [skills, setSkills] = useState("");
  const [photoB64, setPhotoB64] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // alternate gmail OTP
  const [altGmail, setAltGmail] = useState("");
  const [gmailVerified, setGmailVerified] = useState(false);
  const [gmailOtpOpen, setGmailOtpOpen] = useState(false);
  const [gmailOtp, setGmailOtp] = useState("");
  const [sentGmailOtp, setSentGmailOtp] = useState<string | null>(null);
  const [gmailBusy, setGmailBusy] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const me = await api<any>("/auth/me");
      setUser(me.user);
      setProfile(me.profile || {});
      setCompletion(me.profile_completion ?? 0);
      setName(me.user.name || "");
      setPhone(me.profile?.phone || "");
      setCompany(me.profile?.company || "");
      setDesignation(me.profile?.designation || "");
      setYears(String(me.profile?.experience_years ?? me.profile?.years_of_experience ?? ""));
      setLocation(me.profile?.current_location || "");
      const sk = (me.profile?.skills && me.profile.skills.length ? me.profile.skills : me.profile?.expertise) || [];
      setSkills(sk.join(", "));
      setPhotoB64(me.profile?.profile_photo_base64 || null);
      setGmailVerified(!!me.user.gmail_verified);
      setAltGmail(me.user.alternate_gmail || me.profile?.alternate_gmail || "");
    } catch {}
    setRefreshing(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  async function pickPhoto() {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return Alert.alert("Permission needed", "We need photo access to set your profile picture.");
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      base64: true,
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.7,
    });
    if (!res.canceled && res.assets?.[0]?.base64) {
      const mime = res.assets[0].mimeType || "image/jpeg";
      setPhotoB64(`data:${mime};base64,${res.assets[0].base64}`);
    }
  }

  async function save() {
    setBusy(true);
    try {
      const skillsArr = skills.split(",").map((s) => s.trim()).filter(Boolean);
      await api("/profile", {
        method: "PUT",
        body: {
          name,
          phone,
          company,
          designation,
          experience_years: years ? parseInt(years, 10) : null,
          current_location: location,
          skills: skillsArr,
          expertise: skillsArr,
          profile_photo_base64: photoB64,
        },
      });
      Alert.alert("Saved", "Your profile has been updated.");
      load();
    } catch (e: any) {
      Alert.alert("Cannot save", e.message);
    } finally {
      setBusy(false);
    }
  }

  async function sendGmailOtp() {
    const email = (altGmail || "").trim().toLowerCase();
    if (!email.endsWith("@gmail.com") && !email.endsWith("@googlemail.com")) {
      return Alert.alert("Gmail only", "Use a personal @gmail.com address.");
    }
    setGmailBusy(true);
    try {
      const r = await api<any>("/pro/gmail/send-otp", { method: "POST", body: { email } });
      setSentGmailOtp(r?.mock_otp || null);
      setGmailOtpOpen(true);
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally {
      setGmailBusy(false);
    }
  }

  async function verifyGmailOtp() {
    if (!gmailOtp || gmailOtp.length < 4) return Alert.alert("Enter OTP", "Check your Gmail inbox.");
    setGmailBusy(true);
    try {
      await api("/pro/gmail/verify-otp", {
        method: "POST",
        body: { email: altGmail.trim().toLowerCase(), otp: gmailOtp.trim() },
      });
      setGmailOtpOpen(false);
      setGmailOtp("");
      setSentGmailOtp(null);
      Alert.alert("Gmail verified ✅", "You can now host mock interviews.");
      load();
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally {
      setGmailBusy(false);
    }
  }

  async function logout() {
    Alert.alert(
      "Are you sure you want to sign out?",
      undefined,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Yes, Sign Out",
          style: "destructive",
          onPress: async () => {
            await clearSession();
            router.replace("/welcome");
          },
        },
      ],
    );
  }

  const credits = user?.credits ?? 0;
  const initials = (user?.name || user?.email || "?").slice(0, 1).toUpperCase();

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      {/* Top profile card: photo + name + credits chip → wallet */}
      <Card>
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          <TouchableOpacity onPress={pickPhoto} style={styles.avatarWrap}>
            {photoB64 ? (
              <Image source={{ uri: photoB64 }} style={styles.avatarImg} />
            ) : (
              <View style={styles.avatarPlaceholder}><Txt style={{ color: "#fff", fontSize: 24, fontWeight: "700" }}>{initials}</Txt></View>
            )}
            <View style={styles.cameraBadge}><Ionicons name="camera" size={12} color="#fff" /></View>
          </TouchableOpacity>
          <View style={{ flex: 1, marginLeft: 12 }}>
            <Txt variant="h2" numberOfLines={1}>{user?.name || (user?.email || "").split("@")[0]}</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary }}>{designation || "Working Professional"}</Txt>
            <View style={{ flexDirection: "row", alignItems: "center", marginTop: 4 }}>
              <Ionicons name="star" size={14} color="#FFB347" />
              <Txt variant="small" style={{ color: colors.textSecondary, marginLeft: 4 }}>
                {user?.rating ? `${Number(user.rating).toFixed(1)}/10 · ${user.ratings_count} reviews` : "No ratings yet"}
              </Txt>
            </View>
          </View>
          {/* Credits pill — taps into Wallet */}
          <TouchableOpacity testID="credits-pill" onPress={() => router.push("/professional/wallet")} style={styles.creditsPill}>
            <Ionicons name="wallet" size={16} color="#fff" />
            <View style={{ marginLeft: 6 }}>
              <Txt style={{ color: "#fff", fontSize: 10, opacity: 0.8 }}>Available Credits</Txt>
              <Txt style={{ color: "#fff", fontWeight: "800" }} testID="credits-value">{credits}</Txt>
            </View>
          </TouchableOpacity>
        </View>

        {/* Profile completion bar */}
        <View style={{ marginTop: 14 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <Txt variant="label">Profile completion</Txt>
            <Txt variant="label" style={{ color: completion >= 80 ? "#2E7D32" : colors.textSecondary }}>{completion}%</Txt>
          </View>
          <View style={styles.progress}>
            <View style={[styles.progressFill, { width: `${completion}%` }]} />
          </View>
        </View>
      </Card>

      {/* Verification badges */}
      <Card style={{ marginTop: 12 }}>
        <Txt variant="h3">Verification</Txt>
        <View style={styles.badgeRow}>
          <View style={[styles.badge, styles.badgeOk]}>
            <Ionicons name="shield-checkmark" size={16} color="#2E7D32" />
            <Txt variant="small" style={{ color: "#2E7D32", marginLeft: 6, fontWeight: "700" }}>Company Email Verified</Txt>
          </View>
          <View style={[styles.badge, gmailVerified ? styles.badgeOk : styles.badgePending]}>
            <Ionicons name={gmailVerified ? "shield-checkmark" : "alert-circle"} size={16} color={gmailVerified ? "#2E7D32" : "#E65100"} />
            <Txt variant="small" style={{ color: gmailVerified ? "#2E7D32" : "#E65100", marginLeft: 6, fontWeight: "700" }}>
              {gmailVerified ? "Gmail Verified" : "Gmail Pending"}
            </Txt>
          </View>
        </View>
      </Card>

      {/* Personal info */}
      <Card style={{ marginTop: 12 }}>
        <Txt variant="h3">Personal Information</Txt>
        <Input testID="name" label="Full Name" value={name} onChangeText={setName} />
        <Input testID="phone" label="Mobile Number" value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="+91 9876543210" />
        <Input label="Company Email (verified)" value={user?.email || ""} editable={false} />
        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: -8, marginBottom: 8 }}>
          🔒 Read-only after verification.
        </Txt>
        <Input
          testID="alt-gmail"
          label="Alternate Gmail (optional)"
          value={altGmail}
          onChangeText={(v) => { setAltGmail(v); if (gmailVerified) setGmailVerified(false); }}
          keyboardType="email-address"
          autoCapitalize="none"
          placeholder="your.name@gmail.com"
        />
        {!gmailVerified && altGmail ? (
          <Button testID="send-gmail-otp" title="Send verification OTP" variant="secondary" onPress={sendGmailOtp} loading={gmailBusy} style={{ marginTop: -4, marginBottom: 8 }} />
        ) : null}
      </Card>

      {/* Professional info */}
      <Card style={{ marginTop: 12 }}>
        <Txt variant="h3">Professional Details</Txt>
        <Input testID="company" label="Company Name" value={company} onChangeText={setCompany} />
        <Input testID="designation" label="Designation" value={designation} onChangeText={setDesignation} placeholder="Senior Engineer" />
        <Input testID="years" label="Years of Experience" value={years} onChangeText={setYears} keyboardType="number-pad" />
        <Input testID="location" label="Current Location" value={location} onChangeText={setLocation} placeholder="Bangalore" />
        <Input testID="skills" label="Skill Set (comma-separated)" value={skills} onChangeText={setSkills} placeholder="React, System Design, Java" />
      </Card>

      <Button testID="save-profile" title="Save Profile" onPress={save} loading={busy} style={{ marginTop: 14 }} />

      <Button title="Logout" variant="secondary" onPress={logout} style={{ marginTop: 14, marginBottom: 24 }} />

      {/* Gmail OTP modal */}
      <Modal visible={gmailOtpOpen} transparent animationType="slide" onRequestClose={() => setGmailOtpOpen(false)}>
        <View style={styles.modalBg}>
          <View style={styles.modalSheet}>
            <Txt variant="h2">Verify Gmail</Txt>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4, marginBottom: 12 }}>
              Enter the 6-digit OTP sent to {altGmail}.
            </Txt>
            {sentGmailOtp ? (
              <View style={styles.devOtp}>
                <Txt variant="small" style={{ color: "#FF8F00" }}>(Dev) OTP: {sentGmailOtp}</Txt>
              </View>
            ) : null}
            <Input testID="gmail-otp" label="OTP" placeholder="123456" value={gmailOtp} onChangeText={setGmailOtp} keyboardType="number-pad" />
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Button title="Cancel" variant="secondary" onPress={() => setGmailOtpOpen(false)} style={{ flex: 1 }} />
              <Button testID="verify-gmail-otp" title="Verify" onPress={verifyGmailOtp} loading={gmailBusy} style={{ flex: 1 }} />
            </View>
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

const styles = StyleSheet.create({
  avatarWrap: { width: 64, height: 64, position: "relative" },
  avatarImg: { width: 64, height: 64, borderRadius: 32 },
  avatarPlaceholder: { width: 64, height: 64, borderRadius: 32, backgroundColor: "#7C3AED", alignItems: "center", justifyContent: "center" },
  cameraBadge: { position: "absolute", right: 0, bottom: 0, width: 22, height: 22, borderRadius: 11, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.bg },
  creditsPill: { backgroundColor: "#7C3AED", paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.xxl, flexDirection: "row", alignItems: "center" },
  progress: { height: 8, borderRadius: 8, backgroundColor: colors.surfaceAlt, marginTop: 6, overflow: "hidden" },
  progressFill: { height: "100%", borderRadius: 8, backgroundColor: "#7C3AED" },
  badgeRow: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 8 },
  badge: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.md },
  badgeOk: { backgroundColor: "#E8F5E9" },
  badgePending: { backgroundColor: "#FFF3E0" },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  modalSheet: { backgroundColor: colors.bg, padding: 20, borderTopLeftRadius: 24, borderTopRightRadius: 24 },
  devOtp: { backgroundColor: "#FFF8E1", padding: 10, borderRadius: 8, marginBottom: 10 },
});
