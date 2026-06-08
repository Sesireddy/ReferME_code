import React, { useState } from "react";
import { View, Alert } from "react-native";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { Picker } from "@/src/components/Picker";
import { api } from "@/src/lib/api";

const CATEGORY_OPTIONS = [
  { value: "fresher", label: "Fresher" },
  { value: "experienced", label: "Experienced" },
];

export default function ProPostJob() {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [desc, setDesc] = useState("");
  const [location, setLocation] = useState("");
  const [category, setCategory] = useState<string | null>("fresher");
  const [expReq, setExpReq] = useState("0");
  const [skills, setSkills] = useState("");
  const [openings, setOpenings] = useState("1");
  const [busy, setBusy] = useState(false);

  async function post() {
    if (!title || !desc) return Alert.alert("Missing", "Title and description required.");
    if (!category) return Alert.alert("Missing", "Select category.");
    if (category === "experienced" && (!expReq || parseInt(expReq, 10) <= 0))
      return Alert.alert("Missing", "Enter required years of experience for an Experienced role.");
    const open = parseInt(openings || "1", 10);
    if (open < 1) return Alert.alert("Invalid", "Open positions must be at least 1.");
    setBusy(true);
    try {
      await api("/jobs", {
        method: "POST",
        body: {
          title,
          company,
          description: desc,
          location,
          category,
          experience_required: category === "experienced" ? parseInt(expReq, 10) : 0,
          skills_required: skills.split(",").map((s) => s.trim()).filter(Boolean),
          open_positions: open,
        },
      });
      Alert.alert("Posted", "Job is live now.");
      setTitle(""); setCompany(""); setDesc(""); setLocation(""); setExpReq("0"); setSkills(""); setOpenings("1"); setCategory("fresher");
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally { setBusy(false); }
  }

  return (
    <Screen>
      <Txt variant="h1">Post a job opening</Txt>
      <Txt variant="muted">Open jobs at your company — refer candidates and earn ₹1500/hire.</Txt>
      <Card style={{ marginTop: 16 }}>
        <Input testID="pj-title" label="Title" value={title} onChangeText={setTitle} placeholder="Frontend Engineer" />
        <Input testID="pj-company" label="Company Name" value={company} onChangeText={setCompany} placeholder="Acme Corp" />
        <Input testID="pj-desc" label="Description" value={desc} onChangeText={setDesc} multiline placeholder="Role, responsibilities, etc." />
        <Input testID="pj-loc" label="Location" value={location} onChangeText={setLocation} placeholder="Bengaluru / Remote" />
        <Picker
          testID="pj-category"
          label="Category"
          options={CATEGORY_OPTIONS}
          value={category}
          onChange={(v) => setCategory(v as string)}
          placeholder="Fresher / Experienced"
        />
        {category === "experienced" ? (
          <Input testID="pj-exp" label="Years of Experience Required" value={expReq} onChangeText={setExpReq} keyboardType="number-pad" />
        ) : null}
        <Input testID="pj-skills" label="Skill Set (comma-separated)" value={skills} onChangeText={setSkills} placeholder="React Native, TypeScript" />
        <Input testID="pj-openings" label="Number of Open Positions (default 1, max 5)" value={openings} onChangeText={setOpenings} keyboardType="number-pad" />
        <Button testID="pj-submit" title="Post job" loading={busy} onPress={post} />
      </Card>
    </Screen>
  );
}
