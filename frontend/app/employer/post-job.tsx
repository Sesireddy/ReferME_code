import React, { useState } from "react";
import { View, Alert } from "react-native";
import { Screen } from "@/src/components/Screen";
import { Txt } from "@/src/components/Txt";
import { Card } from "@/src/components/Card";
import { Input } from "@/src/components/Input";
import { Button } from "@/src/components/Button";
import { api } from "@/src/lib/api";

export default function PostJob() {
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [location, setLocation] = useState("");
  const [salary, setSalary] = useState("");
  const [skills, setSkills] = useState("");
  const [openings, setOpenings] = useState("1");
  const [busy, setBusy] = useState(false);

  async function post() {
    if (!title || !desc) return Alert.alert("Missing", "Title and description required.");
    setBusy(true);
    try {
      await api("/jobs", {
        method: "POST",
        body: {
          title,
          description: desc,
          location,
          salary_range: salary,
          skills_required: skills.split(",").map((s) => s.trim()).filter(Boolean),
          bulk_openings: parseInt(openings || "1", 10),
        },
      });
      Alert.alert("Posted", "Job is live now.");
      setTitle(""); setDesc(""); setLocation(""); setSalary(""); setSkills(""); setOpenings("1");
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally { setBusy(false); }
  }

  return (
    <Screen>
      <Txt variant="h1">Post a job</Txt>
      <Txt variant="muted">Reach motivated students and professionals.</Txt>
      <Card style={{ marginTop: 16 }}>
        <Input testID="job-title" label="Title" value={title} onChangeText={setTitle} placeholder="Frontend Engineer" />
        <Input testID="job-desc" label="Description" value={desc} onChangeText={setDesc} multiline placeholder="Role, responsibilities, etc." />
        <Input testID="job-location" label="Location" value={location} onChangeText={setLocation} placeholder="Bengaluru / Remote" />
        <Input testID="job-salary" label="Salary range" value={salary} onChangeText={setSalary} placeholder="₹15-25 LPA" />
        <Input testID="job-skills" label="Skills (comma-separated)" value={skills} onChangeText={setSkills} placeholder="React Native, TypeScript" />
        <Input testID="job-openings" label="Number of openings" value={openings} onChangeText={setOpenings} keyboardType="number-pad" />
        <Button testID="post-submit" title="Post job" loading={busy} onPress={post} />
      </Card>
    </Screen>
  );
}
