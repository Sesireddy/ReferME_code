/**
 * Indian mobile number validator + normalizer.
 *
 * Accepts these formats:
 *   8989849312
 *   918989849312
 *   +918989849312
 *   +91-8989849312
 *   +91 8989849312
 *
 * Returns { ok, normalized, error } — normalized is "+91XXXXXXXXXX" on success.
 * Mirrors backend `normalize_indian_mobile` exactly for parity.
 */
export type MobileValidation = { ok: boolean; normalized: string; error: string | null };

export function validateIndianMobile(raw: string | null | undefined): MobileValidation {
  const s = (raw || "").trim();
  if (!s) return { ok: false, normalized: "", error: "Please enter a valid 10-digit Indian mobile number." };

  let digits = s.replace(/\D/g, "");
  // Strip leading country / trunk prefixes
  if (digits.length === 12 && digits.startsWith("91")) digits = digits.slice(2);
  else if (digits.length === 11 && digits.startsWith("0")) digits = digits.slice(1);
  else if (digits.length === 13 && digits.startsWith("091")) digits = digits.slice(3);

  // If user typed a leading '+' with anything other than +91, reject
  if (s.startsWith("+")) {
    const after = s.slice(1).replace(/[-\s]/g, "");
    if (!after.startsWith("91")) {
      return { ok: false, normalized: "", error: "Please enter a valid Indian mobile number with country code +91." };
    }
  }

  if (digits.length !== 10) {
    return { ok: false, normalized: "", error: "Please enter a valid 10-digit Indian mobile number." };
  }
  if (!"6789".includes(digits[0])) {
    return { ok: false, normalized: "", error: "Indian mobile numbers must start with 6, 7, 8, or 9." };
  }
  return { ok: true, normalized: `+91${digits}`, error: null };
}

export function isValidIndianMobile(raw: string | null | undefined): boolean {
  return validateIndianMobile(raw).ok;
}
