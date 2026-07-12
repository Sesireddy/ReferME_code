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
  { value: "15d_or_less", label: "15 Days or Less" },
  { value: "1m", label: "1 Month" },
  { value: "2m", label: "2 Months" },
  { value: "3m", label: "3 Months" },
  { value: "serving", label: "Serving Notice Period" },
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

// Salary range buckets used on Post-a-Job + Job Cards.
export const SALARY_RANGE_OPTIONS = [
  { value: "Not disclosed", label: "Not disclosed" },
  { value: "0-3", label: "0 - 3 Lakhs" },
  { value: "3-5", label: "3 - 5 Lakhs" },
  { value: "5-10", label: "5 - 10 Lakhs" },
  { value: "10-20", label: "10 - 20 Lakhs" },
  { value: "20-50", label: "20 - 50 Lakhs" },
  { value: "50+", label: "50+ Lakhs" },
];

// Industry Type dropdown (Item 2.3).
export const INDUSTRY_OPTIONS = [
  "Software Services/IT",
  "Banking, Financial Services & Insurance",
  "Healthcare/Pharmaceuticals",
  "Education",
  "Telecommunications",
  "Manufacturing",
  "Automotive",
  "Aerospace",
  "Construction/Real Estate",
  "Retail/E-Commerce",
  "Logistics",
  "Media & Entertainment",
  "Hospitality/Travel & Tourism",
  "Energy & Utilities",
  "Consulting",
  "Agriculture",
  "Biotechnology",
].map((v) => ({ value: v, label: v })).concat({ value: "__OTHER__", label: "Other (specify)" });

// Min/Max experience filter dropdowns: 0..15, 15+
export const EXP_FILTER_OPTIONS = [
  ...Array.from({ length: 16 }, (_, i) => ({ value: String(i), label: String(i) })),
  { value: "15+", label: "15+" },
];

// Sort by posted date.
export const JOB_SORT_OPTIONS = [
  { value: "newest", label: "Newest First" },
  { value: "oldest", label: "Oldest First" },
];

// Category filter (adds Intern).
export const JOB_CATEGORY_FILTER_OPTIONS = [
  { value: "", label: "All" },
  { value: "fresher", label: "Fresher" },
  { value: "experienced", label: "Experienced" },
  { value: "intern", label: "Intern" },
];

// Canonical skill set used across Post-a-Job, Mock Interview, Profile and Job filters.
export const SKILL_OPTIONS = [
  "Java", "Python", "JavaScript", "TypeScript", "React", "React Native", "Angular",
  "Vue.js", "Node.js", "Express.js", "Django", "Flask", "Spring Boot", ".NET / C#",
  "PHP", "Ruby on Rails", "Go", "Rust", "Kotlin", "Swift",
  "Oracle SQL", "PL/SQL", "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch",
  "DevOps", "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Terraform", "CI/CD",
  "Testing", "Selenium", "Cypress", "Jest", "Manual QA", "Performance Testing",
  "Data Science", "Data Engineering", "AI/ML", "Deep Learning", "NLP", "Computer Vision",
  "Power BI", "Tableau", "Excel / VBA",
  "Android (Java)", "Android (Kotlin)", "iOS (Swift)", "Flutter",
  "HTML / CSS", "Tailwind CSS", "Next.js",
  "REST APIs", "GraphQL", "Microservices", "System Design",
  "Cybersecurity", "Networking", "Linux Administration",
  "Salesforce", "SAP", "Workday",
  "Product Management", "Project Management", "Business Analysis", "Agile / Scrum",
  "UI / UX Design", "Figma",
].map((v) => ({ value: v, label: v }));

export const GENDER_OPTIONS = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
  { value: "other", label: "Other" },
  { value: "prefer_not_to_say", label: "Prefer not to say" },
];

export const EDUCATION_OPTIONS = [
  "10th Pass",
  "12th Pass",
  "High School",
  "Diploma",
  "Associate Degree",
  "Bachelor's",
  "Master's",
  "Postgraduate Diploma",
  "PhD",
  "Professional Certification",
  "Other",
].map((v) => ({ value: v, label: v }));
