"""Printing service (Plan/07 P1–P5): render clinic-letterhead documents as
standalone HTML for the browser print dialog.

Five doc types x two locales: rx, report, sick_leave, referral, invoice.
Templates use allowlisted ${placeholder} substitution only; the admin editor
rejects scripts, event handlers, external URLs, and unknown placeholders.
"""

import html
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.billing import Invoice
from app.models.comms import PrintTemplate
from app.models.emr import Prescription, PrescriptionItem, Visit, VisitDiagnosis
from app.models.identity import Doctor, PatientProfile, StaffUser
from app.models.scheduling import VisitType
from app.services.settings import get_setting

ALLOWED_KEYS = ("rx", "report", "sick_leave", "referral", "invoice")
ALLOWED_PLACEHOLDERS = re.compile(r"\$\{([a-zA-Z0-9_.]+)\}")

SUSPICIOUS = re.compile(
    r"<\s*script|on(load|click|error|submit|change|mouse|key|focus|blur)\s*=|"
    r"(javascript|data)\s*:|https?://",
    re.IGNORECASE,
)


def validate_template_html(body: str) -> None:
    if SUSPICIOUS.search(body):
        raise AppError("VALIDATION", "template contains forbidden markup (scripts, handlers, URLs)")
    unknown = [
        m.group(1)
        for m in ALLOWED_PLACEHOLDERS.finditer(body)
        if not m.group(1).startswith("clinic.")
        and m.group(1) not in {
            "patient.name", "patient.age", "patient.code", "patient.gender",
            "doctor.name", "doctor.specialty", "date", "rx.items_table",
            "diagnoses", "visit.summary", "invoice.number", "invoice.items_table",
            "invoice.subtotal", "invoice.discount", "invoice.taxable",
            "invoice.tax_rate", "invoice.tax_total", "invoice.total",
            "invoice.paid", "invoice.remaining", "invoice.vat_number",
            "sick.days", "sick.from", "sick.to",
            "referral.to", "referral.reason",
        }
    ]
    if unknown:
        raise AppError("VALIDATION", f"unknown placeholders: {', '.join(sorted(unknown))}")


def get_template(db: Session, key: str, locale: str) -> PrintTemplate:
    template = db.scalar(
        select(PrintTemplate).where(
            PrintTemplate.key == key,
            PrintTemplate.locale == locale,
            PrintTemplate.is_active.is_(True),
        )
    )
    if template is None:
        raise AppError("NOT_FOUND", f"no {locale} template for {key}")
    return template


def _clinic_context(db: Session) -> dict:
    return {
        "clinic.name": get_setting(db, "clinic.name", {}).get("en", "") or "",
        "clinic.name_ar": get_setting(db, "clinic.name", {}).get("ar", "") or "",
        "clinic.address": get_setting(db, "clinic.address", {}).get("en", "") or "",
        "clinic.address_ar": get_setting(db, "clinic.address", {}).get("ar", "") or "",
        "clinic.phones": ", ".join(get_setting(db, "clinic.phones", []) or []),
    }


def _rx_items_table(db: Session, visit_id: int) -> str:
    rx = db.scalar(select(Prescription).where(Prescription.visit_id == visit_id))
    if rx is None:
        return "<p>—</p>"
    items = db.scalars(
        select(PrescriptionItem).where(PrescriptionItem.prescription_id == rx.id).order_by(
            PrescriptionItem.order
        )
    ).all()
    rows = []
    for i, item in enumerate(items, start=1):
        name = item.free_text or ""
        if item.medication_id:
            from app.models.emr import Medication

            med = db.get(Medication, item.medication_id)
            if med:
                name = f"{med.name} {med.strength}"
        rows.append(
            f"<tr><td>{i}</td><td>{html.escape(name)}</td><td>{html.escape(item.dose)}</td>"
            f"<td>{html.escape(item.frequency)}</td><td>{html.escape(item.duration)}</td>"
            f"<td>{html.escape(item.route or '')}</td>"
            f"<td>{html.escape(item.instructions or '')}</td></tr>"
        )
    return (
        "<table><thead><tr><th>#</th><th>Drug</th><th>Dose</th><th>Frequency</th>"
        "<th>Duration</th><th>Route</th><th>Instructions</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _invoice_items_table(db: Session, invoice: Invoice) -> str:
    from app.models.billing import InvoiceItem

    items = db.scalars(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id).order_by(InvoiceItem.id)
    ).all()
    rows = [
        f"<tr><td>{html.escape(i.description)}</td><td>{float(i.qty):g}</td>"
        f"<td>{float(i.unit_price):.2f}</td><td>{float(i.line_total):.2f}</td></tr>"
        for i in items
    ]
    return "<table><thead><tr><th>Item</th><th>Qty</th><th>Unit</th><th>Total</th></tr></thead>" \
           f"<tbody>{''.join(rows)}</tbody></table>"


def _diagnoses_list(db: Session, visit_id: int) -> str:
    rows = db.scalars(
        select(VisitDiagnosis)
        .where(VisitDiagnosis.visit_id == visit_id, VisitDiagnosis.kind == "final")
        .order_by(VisitDiagnosis.order)
    ).all()
    return "<br>".join(html.escape(d.label) for d in rows) if rows else "—"


def _visit_summary(visit: Visit) -> str:
    parts = []
    if visit.chief_complaint:
        parts.append(f"Complaint: {visit.chief_complaint}")
    if visit.findings:
        parts.append(f"Findings: {visit.findings}")
    if visit.plan:
        parts.append(f"Plan: {visit.plan}")
    return "<br>".join(html.escape(p) for p in parts) or "—"


def build_context(db: Session, key: str, entity_id: int) -> dict:
    ctx = _clinic_context(db)
    ctx["date"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d")

    if key == "invoice":
        invoice = db.get(Invoice, entity_id)
        if invoice is None:
            raise AppError("NOT_FOUND", "invoice not found")
        profile = db.get(PatientProfile, invoice.patient_profile_id)
        ctx.update(
            {
                "patient.name": profile.full_name if profile else "",
                "patient.code": profile.code if profile else "",
                "invoice.number": invoice.number,
                "invoice.items_table": _invoice_items_table(db, invoice),
                "invoice.subtotal": f"{float(invoice.subtotal):.2f}",
                "invoice.discount": f"{float(invoice.discount_total):.2f}",
                "invoice.taxable": f"{float(invoice.subtotal) - float(invoice.discount_total):.2f}",
                "invoice.tax_rate": f"{float(invoice.tax_rate):g}",
                "invoice.tax_total": f"{float(invoice.tax_total):.2f}",
                "invoice.total": f"{float(invoice.total):.2f}",
                "invoice.paid": f"{float(invoice.paid_total):.2f}",
                "invoice.vat_number": invoice.vat_number or "",
                "invoice.remaining": _invoice_remaining(invoice),
            }
        )
        return ctx

    visit = db.get(Visit, entity_id)
    if visit is None:
        raise AppError("NOT_FOUND", "visit not found")
    profile = db.get(PatientProfile, visit.patient_profile_id)
    doctor = db.get(Doctor, visit.doctor_id)
    doctor_user = db.get(StaffUser, doctor.staff_user_id) if doctor else None
    visit_type = db.get(VisitType, visit.visit_type_id)
    ctx.update(
        {
            "patient.name": profile.full_name if profile else "",
            "patient.age": str(_age(profile)) if profile and _age(profile) else "",
            "patient.code": profile.code if profile else "",
            "patient.gender": profile.gender or "",
            "doctor.name": doctor_user.full_name if doctor_user else "",
            "doctor.specialty": doctor.specialty if doctor else "",
            "visit.type": visit_type.name if visit_type else "",
            "rx.items_table": _rx_items_table(db, visit.id),
            "diagnoses": _diagnoses_list(db, visit.id),
            "visit.summary": _visit_summary(visit),
            "sick.from": "",
            "sick.to": "",
            "sick.days": "",
            "referral.to": "",
            "referral.reason": "",
        }
    )
    return ctx


def _invoice_remaining(invoice: Invoice) -> str:
    remaining = float(invoice.patient_due) - (
        float(invoice.paid_total) - float(invoice.refunded_total)
    )
    return f"{remaining:.2f}"


def _age(profile: PatientProfile) -> int | None:
    from datetime import date

    if profile.birth_date:
        return (date.today() - profile.birth_date).days // 365
    return None


def _substitute(body: str, context: dict) -> str:
    """string.Template's default pattern rejects dotted names; we want
    `${patient.name}` style placeholders."""

    def repl(match: re.Match) -> str:
        key = match.group(1)
        return str(context.get(key, match.group(0)))

    return re.sub(r"\$\{([A-Za-z0-9_.]+)\}", repl, body)


def render_document(
    db: Session, key: str, entity_id: int, locale: str, ctx: dict | None = None
) -> str:
    template = get_template(db, key, locale)
    context = ctx or build_context(db, key, entity_id)
    body = _substitute(template.body_html, context)
    direction = "rtl" if locale == "ar" else "ltr"
    title = template.title
    return f"""<!DOCTYPE html>
<html lang="{locale}" dir="{direction}">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: 'IBM Plex Sans Arabic', 'Inter', sans-serif; color: #111827; margin: 0; }}
  .sheet {{ max-width: 100%; padding: 12mm; }}
  header.letterhead {{ display: flex; justify-content: space-between; align-items: center;
    border-bottom: 2px solid #0d9488; padding-bottom: 8px; margin-bottom: 16px; }}
  .clinic-name {{ font-size: 18px; font-weight: 700; color: #0d9488; }}
  .meta {{ color: #475569; font-size: 12px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 13px; }}
  th, td {{ border: 1px solid #e2e8f0; padding: 4px 8px; text-align: start; }}
  .totals td {{ border: none; font-weight: 600; }}
  .signature {{ margin-top: 40px; display: flex; justify-content: flex-end; }}
  .sig-line {{ border-top: 1px solid #111827; width: 220px; text-align: center; padding-top: 4px; }}
  @media print {{ .sheet {{ padding: 0; }} }}
</style>
</head>
<body><div class="sheet">
<header class="letterhead">
  <div>
    <div class="clinic-name">{
        html.escape(str(context.get("clinic.name_ar") or context.get("clinic.name") or ""))
    }</div>
    <div class="meta">{html.escape(str(context.get("clinic.address") or ""))}</div>
    <div class="meta">{html.escape(str(context.get("clinic.phones") or ""))}</div>
  </div>
  <div class="meta">{html.escape(title)}<br>{html.escape(str(context.get('date', '')))}</div>
</header>
{body}
</div>
<script>window.addEventListener('load', function() {{
  if (document.fonts && document.fonts.ready) {{
    document.fonts.ready.then(function() {{ setTimeout(function() {{ window.print(); }}, 100); }});
  }} else {{
    setTimeout(function() {{ window.print(); }}, 100);
  }}
}});</script>
</body></html>"""
