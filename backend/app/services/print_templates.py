"""Default print templates (Plan/07 P2) — seeded into the database.
Admin edits live copies in `print_template`; these are the factory defaults.
"""

PRINT_TEMPLATES = {
    "rx": {
        "ar": ("روشتة", """
<p><strong>المريض:</strong> ${patient.name}
<span dir="ltr">(${patient.code})</span> &nbsp; <strong>العمر:</strong> ${patient.age}</p>
<p><strong>التشخيص:</strong> ${diagnoses}</p>
${rx.items_table}
<p><strong>ملاحظات:</strong></p>
<div class="signature"><div class="sig-line">د. ${doctor.name} — ${doctor.specialty}</div></div>
"""),
        "en": ("Prescription", """
<p><strong>Patient:</strong> ${patient.name}
<span dir="ltr">(${patient.code})</span> &nbsp; <strong>Age:</strong> ${patient.age}</p>
<p><strong>Diagnosis:</strong> ${diagnoses}</p>
${rx.items_table}
<div class="signature"><div class="sig-line">Dr. ${doctor.name} — ${doctor.specialty}</div></div>
"""),
    },
    "report": {
        "ar": ("تقرير طبي", """
<p><strong>المريض:</strong> ${patient.name} — ${patient.code}</p>
<p><strong>الشكوى:</strong> ${visit_summary}</p>
<p><strong>التشخيص النهائي:</strong> ${diagnoses}</p>
<div class="signature"><div class="sig-line">د. ${doctor.name}</div></div>
"""),
        "en": ("Medical Report", """
<p><strong>Patient:</strong> ${patient.name} — ${patient.code}</p>
<p><strong>Summary:</strong> ${visit_summary}</p>
<p><strong>Diagnosis:</strong> ${diagnoses}</p>
<div class="signature"><div class="sig-line">Dr. ${doctor.name}</div></div>
"""),
    },
    "sick_leave": {
        "ar": ("إجازة مرضية", """
<p><strong>المريض:</strong> ${patient.name} — ${patient.code}</p>
<p>يُمنح المريض إجازة مرضية لمدة <strong>${sick_days}</strong> يوم
اعتباراً من ${sick_from} حتى ${sick_to}.</p>
<div class="signature"><div class="sig-line">د. ${doctor.name}</div></div>
"""),
        "en": ("Sick Leave", """
<p><strong>Patient:</strong> ${patient.name} — ${patient.code}</p>
<p>Granted sick leave for <strong>${sick_days}</strong> days from ${sick_from} to ${sick_to}.</p>
<div class="signature"><div class="sig-line">Dr. ${doctor.name}</div></div>
"""),
    },
    "referral": {
        "ar": ("خطاب تحويل", """
<p><strong>المريض:</strong> ${patient.name} — ${patient.code}</p>
<p>يُحال المريض إلى: <strong>${referral_to}</strong></p>
<p><strong>السبب:</strong> ${referral_reason}</p>
<div class="signature"><div class="sig-line">د. ${doctor.name}</div></div>
"""),
        "en": ("Referral Letter", """
<p><strong>Patient:</strong> ${patient.name} — ${patient.code}</p>
<p>Referred to: <strong>${referral_to}</strong></p>
<p><strong>Reason:</strong> ${referral_reason}</p>
<div class="signature"><div class="sig-line">Dr. ${doctor.name}</div></div>
"""),
    },
    "invoice": {
        "ar": ("فاتورة", """
<p><strong>المريض:</strong> ${patient.name} <span dir="ltr">(${patient.code})</span></p>
<p><strong>الفاتورة:</strong> ${invoice.number}</p>
${invoice.items_table}
<table class="totals"><tr><td>الإجمالي</td><td>${invoice_total} ج.م</td></tr>
<tr><td>الخصم</td><td>${invoice_discount}</td></tr>
<tr><td>المدفوع</td><td>${invoice_paid}</td></tr>
<tr><td>المتبقي</td><td>${invoice_remaining}</td></tr></table>
"""),
        "en": ("Invoice", """
<p><strong>Patient:</strong> ${patient.name} <span dir="ltr">(${patient.code})</span></p>
<p><strong>Invoice:</strong> ${invoice.number}</p>
${invoice.items_table}
<table class="totals"><tr><td>Total</td><td>${invoice_total} EGP</td></tr>
<tr><td>Discount</td><td>${invoice_discount}</td></tr>
<tr><td>Paid</td><td>${invoice_paid}</td></tr>
<tr><td>Remaining</td><td>${invoice_remaining}</td></tr></table>
"""),
    },
}

