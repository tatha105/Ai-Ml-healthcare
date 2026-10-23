import type { ClaimDraft } from "./types";

export type Scenario = ClaimDraft & {
  id: string;
  label: string;
  hint: string;
};

const FORM = [
  "Admission form",
  "Hospital: CityCare Hospital",
  "The admitting doctor has signed this form.",
  "Requested cashless inpatient treatment.",
].join("\n");

export const scenarios: Scenario[] = [
  {
    id: "surgery",
    label: "Routine surgery",
    hint: "In network, room rent inside the Gold cap",
    member_id: "MBR-1001",
    hospital_id: "HSP-CITY",
    admitted_at: "2026-10-14T09:30",
    diagnosis: "Acute appendicitis",
    treatment: "Laparoscopic appendectomy",
    estimated_amount: 85000,
    room_rent_per_day: 4000,
    stay_days: 3,
    document_name: "admission-form.txt",
    document_text: FORM,
  },
  {
    id: "room",
    label: "Room-rent cap",
    hint: "Silver plan, rent above Rs 3,000 a day",
    member_id: "MBR-1002",
    hospital_id: "HSP-CITY",
    admitted_at: "2026-10-14T11:00",
    diagnosis: "Dengue fever",
    treatment: "Inpatient medical management",
    estimated_amount: 96000,
    room_rent_per_day: 8000,
    stay_days: 4,
    document_name: "admission-form.txt",
    document_text: FORM.replace("CityCare Hospital", "CityCare Hospital\nRoom category: single"),
  },
  {
    id: "wait",
    label: "Waiting period",
    hint: "Arthroscopy inside the 90-day specified-illness wait",
    member_id: "MBR-1003",
    hospital_id: "HSP-CITY",
    admitted_at: "2026-10-10T08:15",
    diagnosis: "Knee arthroscopy",
    treatment: "Arthroscopic repair",
    estimated_amount: 140000,
    room_rent_per_day: 4500,
    stay_days: 2,
    document_name: "admission-form.txt",
    document_text: FORM,
  },
  {
    id: "form",
    label: "Unreadable form",
    hint: "No legible admission note, so coverage is not assessed",
    member_id: "MBR-1004",
    hospital_id: "HSP-CITY",
    admitted_at: "2026-10-14T16:40",
    diagnosis: "Chest pain",
    treatment: "Observation",
    estimated_amount: 42000,
    room_rent_per_day: 4000,
    stay_days: 2,
    document_name: "admission-scan.pdf",
    document_text: "",
  },
  {
    id: "network",
    label: "Out of network",
    hint: "Lakeside Clinic is outside the cashless network",
    member_id: "MBR-1001",
    hospital_id: "HSP-LAKE",
    admitted_at: "2026-10-14T09:30",
    diagnosis: "Acute appendicitis",
    treatment: "Laparoscopic appendectomy",
    estimated_amount: 85000,
    room_rent_per_day: 4000,
    stay_days: 3,
    document_name: "admission-form.txt",
    document_text: FORM.replace("CityCare Hospital", "Lakeside Clinic"),
  },
];
