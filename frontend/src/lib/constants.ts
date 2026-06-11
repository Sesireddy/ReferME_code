// Shared dropdown option lists used across forms.
export const EXPERIENCE_OPTIONS = [
  ...Array.from({ length: 30 }, (_, i) => ({ value: String(i), label: `${i} ${i === 1 ? "Year" : "Years"}` })),
  { value: "30+", label: "30+ Years" },
];

export const METRO_CITIES = [
  "Bangalore", "Hyderabad", "Chennai", "Mumbai", "Pune", "Delhi", "Noida", "Gurgaon",
  "Kolkata", "Kochi", "Ahmedabad", "Jaipur", "Lucknow", "Bhubaneswar", "Visakhapatnam",
  "Coimbatore", "Chandigarh", "Indore",
];
export const LOCATION_OPTIONS = [
  ...METRO_CITIES.map((c) => ({ value: c, label: c })),
  { value: "__OTHER__", label: "Others (specify)" },
];

export const EDUCATION_OPTIONS = [
  "B.Tech", "Degree (B.A)", "Degree (B.Com)", "Degree (B.Sc)", "BBA", "BCA",
  "B.Ed", "B.Pharma", "LLB", "Diploma", "MCA", "M.Sc", "M.Com",
].map((e) => ({ value: e, label: e })).concat({ value: "__OTHER__", label: "Other (specify)" });

export const GENDER_OPTIONS = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
  { value: "other", label: "Other" },
  { value: "prefer_not_to_say", label: "Prefer Not To Say" },
];

export const PREFERRED_ROLE_OPTIONS = [
  { value: "fresher", label: "Fresher" },
  { value: "experienced", label: "Experienced" },
  { value: "intern", label: "Intern" },
];

export const CURRENTLY_WORKING_OPTIONS = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];

export const NOTICE_PERIOD_OPTIONS = [
  { value: "immediate", label: "Immediate" },
  { value: "15d", label: "15 Days" },
  { value: "30d", label: "30 Days" },
  { value: "60d", label: "60 Days" },
  { value: "90d", label: "90 Days" },
];

export const ANNUAL_SALARY_OPTIONS = [
  { value: "0-3", label: "0 - 3 LPA" },
  { value: "3-6", label: "3 - 6 LPA" },
  { value: "6-10", label: "6 - 10 LPA" },
  { value: "10-15", label: "10 - 15 LPA" },
  { value: "15+", label: "15+ LPA" },
];

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
  .map((m, i) => ({ value: String(i + 1).padStart(2, "0"), label: m }));

export const YEARS_2000_2030 = Array.from({ length: 31 }, (_, i) => ({ value: String(2000 + i), label: String(2000 + i) }));
export const YEARS_2010_2030 = Array.from({ length: 21 }, (_, i) => ({ value: String(2010 + i), label: String(2010 + i) }));
