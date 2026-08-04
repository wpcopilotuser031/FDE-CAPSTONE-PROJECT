"""
Generate sample referral PDF documents for demonstration.
Run once: python scripts/generate_sample_pdfs.py
Produces: data/referral_docs/referral_cardiology.pdf
          data/referral_docs/referral_orthopedics.pdf
"""
from pathlib import Path

from fpdf import FPDF  # fpdf2


OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "referral_docs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _add_header(pdf: FPDF, title: str) -> None:
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, title, ln=True)
    pdf.set_draw_color(0, 95, 115)
    pdf.set_line_width(0.6)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)


def _field(pdf: FPDF, label: str, value: str) -> None:
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(50, 7, label + ":", ln=False)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, value, ln=True)


def _section(pdf: FPDF, title: str) -> None:
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(224, 240, 243)
    pdf.cell(0, 8, "  " + title, ln=True, fill=True)
    pdf.ln(2)


def _body(pdf: FPDF, text: str) -> None:
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, text)
    pdf.ln(2)


# ── Document 1: Cardiology Referral ──────────────────────────────────────────

def build_cardiology_pdf() -> None:
    pdf = FPDF()
    pdf.set_margins(10, 12, 10)
    pdf.add_page()

    _add_header(pdf, "CARDIOLOGY REFERRAL NOTE")

    _section(pdf, "Patient & Referral Information")
    _field(pdf, "Document ID", "PDF-CARD-001")
    _field(pdf, "Date", "2026-08-04")
    _field(pdf, "Patient", "John Doe  |  DOB: 1968-04-22  |  MRN: PT-10042")
    _field(pdf, "Referring Provider", "Dr. Sarah Mitchell, MD (NPI: 1234567890)")
    _field(pdf, "Referred To", "Cardiology Specialist")
    _field(pdf, "Insurance", "Aetna PPO  |  Member ID: AET-10042-X")

    _section(pdf, "Reason for Referral")
    _body(pdf,
        "Patient presents with progressively worsening chest pain on exertion and "
        "shortness of breath over the past 3 months. Recent resting ECG showed "
        "premature atrial complexes. Patient has known essential hypertension and "
        "type 2 diabetes mellitus. Requesting full cardiology evaluation for "
        "possible coronary artery disease workup.")

    _section(pdf, "Active Diagnoses (ICD-10)")
    diagnoses = [
        ("I10",    "Essential (primary) hypertension"),
        ("E11.9",  "Type 2 diabetes mellitus without complications"),
        ("R07.9",  "Chest pain, unspecified"),
        ("E78.5",  "Hyperlipidemia, unspecified"),
        ("I48.0",  "Paroxysmal atrial fibrillation"),
    ]
    pdf.set_font("Helvetica", "", 10)
    for code, desc in diagnoses:
        pdf.cell(30, 7, code, ln=False)
        pdf.cell(0, 7, desc, ln=True)

    _section(pdf, "Procedures Performed / Requested (CPT)")
    procedures = [
        ("93000", "Electrocardiogram, routine 12-lead ECG"),
        ("80053", "Comprehensive metabolic panel"),
        ("83036", "Hemoglobin A1C"),
        ("93306", "Echocardiography, transthoracic (requested)"),
        ("99214", "Office visit, established patient, high complexity"),
    ]
    pdf.set_font("Helvetica", "", 10)
    for code, desc in procedures:
        pdf.cell(30, 7, code, ln=False)
        pdf.cell(0, 7, desc, ln=True)

    _section(pdf, "Clinical Notes")
    _body(pdf,
        "BP: 148/92 mmHg. HbA1c: 7.4%. LDL: 142 mg/dL. Patient reports "
        "palpitations lasting 20-30 seconds. No prior cardiac history. "
        "Family history: father had MI at age 58. "
        "Current medications: Metformin 1000mg BID, Lisinopril 10mg QD, "
        "Atorvastatin 40mg QD. Please evaluate and manage accordingly.")

    out = OUTPUT_DIR / "referral_cardiology.pdf"
    pdf.output(str(out))
    print(f"Created: {out}")


# ── Document 2: Orthopedic / Knee Arthroplasty Referral ──────────────────────

def build_orthopedics_pdf() -> None:
    pdf = FPDF()
    pdf.set_margins(10, 12, 10)
    pdf.add_page()

    _add_header(pdf, "ORTHOPEDIC SURGICAL REFERRAL NOTE")

    _section(pdf, "Patient & Referral Information")
    _field(pdf, "Document ID", "PDF-ORTHO-001")
    _field(pdf, "Date", "2026-08-04")
    _field(pdf, "Patient", "Robert Kim  |  DOB: 1952-03-14  |  MRN: PT-30091")
    _field(pdf, "Referring Provider", "Dr. Nadia Chen, MD (NPI: 1122334455)")
    _field(pdf, "Referred To", "Orthopedic Surgery - Total Knee Arthroplasty")
    _field(pdf, "Insurance", "Medicare Advantage - BlueCross PPO")
    _field(pdf, "Auth Number", "AUTH-2026-KIM-0991")

    _section(pdf, "Reason for Referral")
    _body(pdf,
        "74-year-old male with end-stage bilateral knee osteoarthritis, primarily "
        "affecting the right knee, with severe functional limitation. Conservative "
        "management including 12 sessions of physical therapy and bilateral "
        "corticosteroid injections has been exhausted over 18 months. "
        "Requesting orthopedic surgical consultation for total knee arthroplasty. "
        "Pre-operative cardiology clearance obtained (Dr. Harrison, 2026-07-15).")

    _section(pdf, "Active Diagnoses (ICD-10)")
    diagnoses = [
        ("M17.11", "Primary osteoarthritis, right knee"),
        ("M17.12", "Primary osteoarthritis, left knee"),
        ("G89.29", "Other chronic pain"),
        ("I10",    "Essential (primary) hypertension"),
        ("I50.9",  "Heart failure, unspecified"),
        ("D64.9",  "Anemia, unspecified"),
    ]
    pdf.set_font("Helvetica", "", 10)
    for code, desc in diagnoses:
        pdf.cell(30, 7, code, ln=False)
        pdf.cell(0, 7, desc, ln=True)

    _section(pdf, "Procedures (CPT)")
    procedures = [
        ("27447", "Total knee arthroplasty (planned)"),
        ("20610", "Corticosteroid injection, knee joint"),
        ("73565", "X-ray knee, 4 views bilateral"),
        ("85025", "Complete blood count (CBC)"),
        ("80053", "Comprehensive metabolic panel"),
        ("97001", "Physical therapy evaluation (12 sessions completed)"),
        ("99213", "Office visit, established patient, moderate complexity"),
    ]
    pdf.set_font("Helvetica", "", 10)
    for code, desc in procedures:
        pdf.cell(30, 7, code, ln=False)
        pdf.cell(0, 7, desc, ln=True)

    _section(pdf, "Clinical Summary")
    _body(pdf,
        "Patient has KL Grade IV changes bilaterally on plain films (bone-on-bone "
        "right knee, Grade III left knee). BMI: 29.4. Pain score 8/10 with "
        "ambulation. Pre-operative labs ordered including CBC (CPT 85025), "
        "BMP (CPT 80053), and coagulation panel. "
        "Patient counseled on risks, benefits, and alternatives to surgery.")

    out = OUTPUT_DIR / "referral_orthopedics.pdf"
    pdf.output(str(out))
    print(f"Created: {out}")


if __name__ == "__main__":
    build_cardiology_pdf()
    build_orthopedics_pdf()
    print("Done. Both sample PDFs are in data/referral_docs/")
