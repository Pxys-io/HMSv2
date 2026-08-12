"""Permission catalog (Plan/14 A1) — the single source of truth.

Used by: seed (system-role matrix), tests (parity), and the admin roles UI
(via GET /api/permissions). Groups map to UI module sections.
"""

PERMISSION_GROUPS: dict[str, list[tuple[str, str, str]]] = {
    "patient": [
        ("patient.view", "View patients", "عرض المرضى"),
        ("patient.edit", "Edit patients", "تعديل المرضى"),
        ("patient.merge", "Merge/duplicates", "دمج الملفات المكررة"),
        ("patient.archive", "Archive/unarchive", "أرشفة/استعادة"),
    ],
    "appointment": [
        ("appointment.view", "View appointments", "عرض المواعيد"),
        ("appointment.create", "Create appointments", "إنشاء المواعيد"),
        ("appointment.edit", "Edit/move appointments", "تعديل المواعيد"),
        ("appointment.cancel", "Cancel appointments", "إلغاء المواعيد"),
        ("appointment.no_show", "Mark no-show", "تسجيل عدم الحضور"),
    ],
    "queue": [
        ("queue.view", "View queue", "عرض قائمة الانتظار"),
        ("queue.checkin", "Check in", "تسجيل الوصول"),
        ("queue.call", "Call next", "النداء على التالي"),
        ("queue.start", "Start visits", "بدء الكشف"),
        ("queue.complete", "Complete visits", "إنهاء الكشف"),
        ("queue.move", "Reorder queue", "إعادة الترتيب"),
        ("queue.close_day", "Close day", "إغلاق اليوم"),
    ],
    "emr": [
        ("emr.view", "View EMR", "عرض الملف الطبي"),
        ("emr.write", "Write EMR", "تعديل الملف الطبي"),
        ("emr.prescribe", "Prescribe", "وصف الأدوية"),
        ("emr.attach", "Attachments", "المرفقات"),
        ("emr.labs", "Labs", "التحاليل"),
    ],
    "billing": [
        ("billing.view", "View billing", "عرض الفواتير"),
        ("billing.invoice", "Create invoices", "إنشاء الفواتير"),
        ("billing.discount", "Discounts", "الخصومات"),
        ("billing.payment", "Record payments", "تسجيل المدفوعات"),
        ("billing.refund", "Refunds", "المرتجعات"),
        ("billing.manage_pricing", "Manage pricing", "إدارة الأسعار"),
        ("billing.expense", "Expenses", "المصروفات"),
    ],
    "inventory": [
        ("inventory.view", "View inventory", "عرض المخزون"),
        ("inventory.edit", "Edit inventory", "تعديل المخزون"),
        ("inventory.purchase", "Purchases", "المشتريات"),
        ("inventory.dispense", "Dispense", "صرف الأدوية"),
    ],
    "hr": [
        ("hr.attendance", "Attendance", "الحضور"),
        ("hr.leave", "Leaves", "الإجازات"),
        ("hr.payroll", "Payroll", "الرواتب"),
    ],
    "ops": [
        ("ops.task", "Tasks", "المهام"),
        ("ops.dashboard", "Dashboard", "لوحة المؤشرات"),
        ("ops.activity_view", "Activity feed", "سجل النشاط"),
        ("ops.tag", "Tags", "الوسوم"),
        ("ops.referral", "Referrals", "التحويلات"),
        ("ops.lab_order", "Lab orders", "طلبات التحاليل"),
        ("ops.communication", "Communication log", "سجل التواصل"),
        ("ops.duplicates", "Duplicate detection", "كشف المكرر"),
    ],
    "chat": [
        ("chat.view", "View chat", "عرض المحادثات"),
        ("chat.reply", "Reply to chat", "الرد على المحادثات"),
    ],
    "report": [
        ("report.all", "All reports", "كل التقارير"),
        ("report.own", "Own reports", "تقارير شخصية"),
        ("report.cashier", "Cashier reports", "تقارير الكاشير"),
    ],
    "admin": [
        ("admin.users", "Manage users", "إدارة المستخدمين"),
        ("admin.roles", "Manage roles", "إدارة الأدوار"),
        ("admin.settings", "Manage settings", "إدارة الإعدادات"),
        ("admin.audit", "Audit log", "سجل التدقيق"),
        ("admin.custom_fields", "Custom fields", "الحقول المخصصة"),
        ("admin.templates", "Print templates", "قوالب الطباعة"),
        ("admin.schedule_manage", "Manage schedules", "إدارة الجداول"),
    ],
}

ALL_PERMISSIONS: list[str] = [
    code
    for group in PERMISSION_GROUPS.values()
    for code, _label, _label_ar in group
]

PERMISSION_LABELS: dict[str, tuple[str, str]] = {
    code: (label, label_ar)
    for group in PERMISSION_GROUPS.values()
    for code, label, label_ar in group
}

# ------------------------------------------------------------------ matrix


def _perm_set(*codes: str) -> list[str]:
    return list(codes)


SYSTEM_ROLE_MATRIX: dict[str, dict[str, list[str]]] = {
    "admin": {"name": "Admin", "name_ar": "مدير النظام", "permissions": ALL_PERMISSIONS},
    "doctor": {
        "name": "Doctor",
        "name_ar": "طبيب",
        "permissions": [
            "patient.view", "patient.edit",
            "appointment.view", "appointment.create", "appointment.edit",
            "queue.view", "queue.call", "queue.start", "queue.complete",
            "emr.view", "emr.write", "emr.prescribe", "emr.attach", "emr.labs",
            "billing.view", "billing.discount",
            "inventory.view", "inventory.dispense",
            "ops.task", "ops.dashboard", "ops.referral", "ops.lab_order",
            "ops.activity_view",
            "chat.view",
            "report.own",
            "hr.attendance",
        ],
    },
    "secretary": {
        "name": "Secretary",
        "name_ar": "سكرتارية",
        "permissions": [
            "patient.view", "patient.edit",
            "appointment.view", "appointment.create", "appointment.edit",
            "appointment.cancel", "appointment.no_show",
            "queue.view", "queue.checkin", "queue.call", "queue.start",
            "queue.complete", "queue.move", "queue.close_day",
            "billing.view", "billing.invoice", "billing.payment",
            "billing.discount", "billing.expense",
            "inventory.view",
            "ops.task", "ops.dashboard", "ops.referral", "ops.lab_order",
            "ops.activity_view", "ops.tag", "ops.communication",
            "chat.view", "chat.reply",
            "report.cashier",
            "hr.attendance",
        ],
    },
}
