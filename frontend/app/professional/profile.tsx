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
import { ConfirmDialog } from "@/src/components/ConfirmDialog";
import { Picker } from "@/src/components/Picker";
import { ScreenTitle } from "@/src/components/ScreenTitle";
import { ProfileMenuSheet, MenuItem } from "@/src/components/ProfileMenuSheet";
import { validateIndianMobile } from "@/src/lib/phone";
import { EXPERIENCE_OPTIONS, LOCATION_OPTIONS } from "@/src/lib/constants";

function maskPhone(p?: string): string {
  if (!p) return "";
  // keep leading non-digits, mask middle, reveal last 4 digits
  const digits = p.replace(/\D/g, "");
  if (digits.length <= 4) return p;
  const last4 = digits.slice(-4);
  const masked = "X".repeat(Math.max(4, digits.length - 4)) + last4;
  // Preserve any country-code prefix like +91 if present
  if (p.startsWith("+")) {
    const cc = p.slice(0, p.indexOf(" ") >= 0 ? p.indexOf(" ") : 3);
    return `${cc} ${masked}`;
  }
  return masked;
}

export default function ProProfile() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [profile, setProfile] = useState<any>({});
  const [completion, setCompletion] = useState<number>(0);
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [editingPhone, setEditingPhone] = useState(false);

  // editable
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  // Mobile verification state (mirrors student profile)
  const [phoneVerified, setPhoneVerified] = useState(false);
  const [verifiedPhone, setVerifiedPhone] = useState("");
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [sendingOtp, setSendingOtp] = useState(false);
  const [verifyingOtp, setVerifyingOtp] = useState(false);
  const [otpModal, setOtpModal] = useState<{ open: boolean; mockOtp: string }>({ open: false, mockOtp: "" });
  const [otpInput, setOtpInput] = useState("");
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
  const [signoutOpen, setSignoutOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [missingDialogOpen, setMissingDialogOpen] = useState(false);
  const [savedOk, setSavedOk] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const me = await api<any>("/auth/me");
      setUser(me.user);
      setProfile(me.profile || {});
      setCompletion(me.profile_completion ?? 0);
      setMissingFields(me.missing_fields || []);
      setName(me.user.name || "");
      setPhone(me.profile?.phone || "");
      setPhoneVerified(!!me.profile?.phone_verified);
      setVerifiedPhone(me.profile?.phone_verified ? (me.profile?.phone || "") : "");
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
    // 1) Validate mandatory fields client-side first (mirror of backend pro_missing_fields)
    const localMissing: string[] = [];
    if (!name.trim()) localMissing.push("Full Name");
    if (!phone.trim()) localMissing.push("Mobile Number");
    if (!gmailVerified || !altGmail.trim()) localMissing.push("Alternate Gmail Address");
    if (!company.trim()) localMissing.push("Company Name");
    if (!designation.trim()) localMissing.push("Designation");
    if (!years.trim() || parseInt(years, 10) <= 0) localMissing.push("Total Experience");
    if (!location.trim()) localMissing.push("Current Location");
    if (skills.split(",").map((s) => s.trim()).filter(Boolean).length === 0) localMissing.push("Skill Set");
    if (!photoB64) localMissing.push("Profile Photo");
    if (localMissing.length > 0) {
      setMissingFields(localMissing);
      setMissingDialogOpen(true);
      return;
    }
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
          experience_years: parseInt(years, 10),
          current_location: location,
          skills: skillsArr,
          expertise: skillsArr,
          profile_photo_base64: photoB64,
        },
      });
      setSavedOk(true);
      setMissingDialogOpen(false);
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
    setSignoutOpen(true);
  }
  async function confirmLogout() {
    setSignoutOpen(false);
    await clearSession();
    router.replace("/welcome");
  }

  const credits = user?.credits ?? 0;
  const initials = (user?.name || user?.email || "?").slice(0, 1).toUpperCase();

  return (
    <Screen refreshing={refreshing} onRefresh={load}>
      <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 12, gap: 8 }}>
        <TouchableOpacity
          testID="pro-menu-btn"
          onPress={() => setMenuOpen(true)}
          hitSlop={10}
          style={styles.menuBtn}
          accessibilityRole="button"
          accessibilityLabel="Open menu"
        >
          <Ionicons name="menu" size={22} color={colors.textPrimary} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <ScreenTitle
            title="Profile"
            icon="person-circle"
            color="#7C3AED"
            right={
              <TouchableOpacity testID="profile-logout-btn" onPress={logout} hitSlop={10}>
                <Ionicons name="log-out-outline" size={24} color={colors.textPrimary} />
              </TouchableOpacity>
            }
          />
        </View>
      </View>
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

      {missingDialogOpen && missingFields.length > 0 ? (
        <Card style={{ marginTop: 12, backgroundColor: "#FFF3E0", borderColor: "#FFB74D", borderWidth: 1 }}>
          <Txt variant="h3" style={{ color: "#E65100" }}>Please complete the following fields:</Txt>
          {missingFields.map((f) => (
            <Txt key={f} variant="small" style={{ color: "#BF360C", marginTop: 4 }}>• {f}</Txt>
          ))}
        </Card>
      ) : null}

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
        <Input
          testID="phone"
          label="Mobile Number"
          value={editingPhone ? phone : maskPhone(phone)}
          onChangeText={(v) => {
            setPhone(v);
            // Any edit invalidates current verification + clears stale error
            if (v.trim() !== verifiedPhone.trim()) setPhoneVerified(false);
            else setPhoneVerified(true);
            const r = validateIndianMobile(v);
            setPhoneError(!v || r.ok ? null : r.error);
          }}
          onFocus={() => setEditingPhone(true)}
          onBlur={() => setEditingPhone(false)}
          keyboardType="phone-pad"
          placeholder="+91 9876543210"
        />
        {phoneError ? (
          <Txt variant="small" style={{ color: colors.error, marginTop: -8, marginBottom: 6 }}>{phoneError}</Txt>
        ) : null}
        {phoneVerified && phone && verifiedPhone === phone ? (
          <View style={styles.verifiedRow}>
            <Ionicons name="checkmark-circle" size={16} color={colors.success} />
            <Txt variant="small" style={{ color: colors.success, fontWeight: "700", marginLeft: 4 }}>
              Mobile Number Verified
            </Txt>
          </View>
        ) : (
          <Button
            testID="send-phone-otp"
            title={sendingOtp ? "Sending OTP…" : "Verify Mobile Number"}
            variant="secondary"
            onPress={async () => {
              const v = validateIndianMobile(phone);
              if (!v.ok) { Alert.alert("Invalid number", v.error || "Please enter a valid mobile number."); return; }
              setSendingOtp(true);
              try {
                const res = await api<any>("/profile/phone/send-otp", { method: "POST", body: { phone: v.normalized } });
                setOtpInput("");
                setOtpModal({ open: true, mockOtp: res.mock_otp || "" });
              } catch (e: any) {
                Alert.alert("Could not send OTP", e.message || String(e));
              } finally { setSendingOtp(false); }
            }}
            disabled={!validateIndianMobile(phone).ok}
            style={{ marginTop: -4, marginBottom: 8 }}
          />
        )}
        <Input label="Company Email (Used Only For Verification)" value={user?.email || ""} editable={false} />
        <Txt variant="small" style={{ color: colors.textSecondary, marginTop: -8, marginBottom: 8 }}>
          🔒 Read-only after verification.
        </Txt>
        <Input
          testID="alt-gmail"
          label="Alternate Gmail (Used for Communication)"
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
        <Picker
          testID="years"
          label="Your Total Experience"
          options={EXPERIENCE_OPTIONS}
          value={years}
          onChange={(v) => setYears(v as string)}
          placeholder="Select experience"
        />
        <Picker
          testID="location"
          label="Current Location"
          options={LOCATION_OPTIONS}
          value={LOCATION_OPTIONS.some((o) => o.value === location) ? location : (location ? "__OTHER__" : "")}
          onChange={(v) => setLocation(v === "__OTHER__" ? (location && !LOCATION_OPTIONS.some((o) => o.value === location) ? location : "") : (v as string))}
          placeholder="Select city"
        />
        {(location === "__OTHER__" || (location && !LOCATION_OPTIONS.some((o) => o.value === location))) ? (
          <Input testID="location-other" label="Specify location" value={location === "__OTHER__" ? "" : location} onChangeText={setLocation} placeholder="Enter your city" />
        ) : null}
        <Input testID="skills" label="Skill Set (comma-separated)" value={skills} onChangeText={setSkills} placeholder="React, System Design, Java" />
      </Card>

      <Button testID="save-profile" title={completion >= 100 ? "Edit Profile" : "Save Profile"} onPress={save} loading={busy} style={{ marginTop: 14 }} />

      <ConfirmDialog
        visible={savedOk}
        title="Profile saved successfully."
        confirmLabel="OK"
        cancelLabel=""
        onCancel={() => setSavedOk(false)}
        onConfirm={() => setSavedOk(false)}
      />

      <Button
        testID="sign-out-btn"
        title="Sign Out"
        variant="outline"
        onPress={logout}
        style={{ marginTop: 14, marginBottom: 24, borderColor: colors.error }}
      />

      <ConfirmDialog
        visible={signoutOpen}
        title="Are you sure you want to sign out?"
        confirmLabel="Yes, Sign Out"
        cancelLabel="Cancel"
        destructive
        onCancel={() => setSignoutOpen(false)}
        onConfirm={confirmLogout}
      />

      {/* Phone OTP Modal */}
      <Modal visible={otpModal.open} transparent animationType="slide" onRequestClose={() => setOtpModal({ open: false, mockOtp: "" })}>
        <View style={styles.modalBg}>
          <View style={styles.modalSheet}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Txt variant="h3">Verify mobile number</Txt>
              <TouchableOpacity onPress={() => setOtpModal({ open: false, mockOtp: "" })} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.textPrimary} />
              </TouchableOpacity>
            </View>
            <Txt variant="small" style={{ color: colors.textSecondary, marginTop: 4 }}>
              Enter the 6-digit code we sent to {validateIndianMobile(phone).normalized || phone}.
            </Txt>
            {otpModal.mockOtp ? (
              <Txt variant="small" style={{ marginTop: 6, color: colors.accent }}>Mock OTP: {otpModal.mockOtp}</Txt>
            ) : null}
            <Input
              testID="phone-otp-input"
              label="OTP"
              placeholder="123456"
              keyboardType="number-pad"
              value={otpInput}
              onChangeText={setOtpInput}
            />
            <Button
              testID="phone-otp-submit"
              title={verifyingOtp ? "Verifying…" : "Verify"}
              onPress={async () => {
                if (!otpInput.trim() || otpInput.trim().length < 4) { Alert.alert("Enter OTP", "Please enter the 6-digit code."); return; }
                const norm = validateIndianMobile(phone).normalized || phone.trim();
                setVerifyingOtp(true);
                try {
                  const res = await api<any>("/profile/phone/verify-otp", { method: "POST", body: { phone: norm, otp: otpInput.trim() } });
                  setPhoneVerified(true);
                  setPhone(norm);
                  setVerifiedPhone(norm);
                  setOtpModal({ open: false, mockOtp: "" });
                  setOtpInput("");
                  if (res.user) setUser((prev: any) => ({ ...(prev || {}), ...res.user, profile: res.profile || prev?.profile }));
                  Alert.alert("Verified", "Your mobile number has been verified.");
                } catch (e: any) {
                  Alert.alert("OTP failed", e.message || "Incorrect or expired code.");
                } finally { setVerifyingOtp(false); }
              }}
              style={{ marginTop: 6 }}
            />
          </View>
        </View>
      </Modal>

      <ProfileMenuSheet
        visible={menuOpen}
        onClose={() => setMenuOpen(false)}
        topOffset={86}
        items={
          [
            { key: "home", label: "Home", icon: "home", color: "#7C3AED", onPress: () => router.push("/professional/dashboard") },
            { key: "jobs", label: "My Posted Jobs", icon: "briefcase", color: "#2563EB", onPress: () => router.push("/professional/my-jobs") },
            { key: "interviews", label: "My Mock Interviews", icon: "mic", color: "#0EA5E9", onPress: () => router.push("/professional/my-mock-interviews") },
            { key: "leaderboard", label: "LeaderBoard", icon: "trophy", color: "#F59E0B", onPress: () => router.push("/professional/my-leaderboard") },
            { key: "refer", label: "Refer a Friend", icon: "people", color: "#22C55E", onPress: () => router.push("/professional/refer") },
          ] as MenuItem[]
        }
      />

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
  menuBtn: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  verifiedRow: { flexDirection: "row", alignItems: "center", marginTop: -8, marginBottom: 8, paddingVertical: 6, paddingHorizontal: 10, borderRadius: 8, backgroundColor: colors.success + "1A", alignSelf: "flex-start" },
  devOtp: { backgroundColor: "#FFF8E1", padding: 10, borderRadius: 8, marginBottom: 10 },
});
