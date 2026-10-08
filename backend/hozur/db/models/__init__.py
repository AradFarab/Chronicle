"""All tables. Import from here so every model is registered on Base.metadata."""

from hozur.db.models.access import AppUser, UserRole, UserSession
from hozur.db.models.attendance import AttendancePeriod, DailyAttendance, DailyAttendanceLeave
from hozur.db.models.calendar import CalendarYear, Holiday
from hozur.db.models.devices import (
	AttendanceDevice,
	DeviceUserMap,
	PunchImport,
	PunchImportTemplate,
	RawPunch,
)
from hozur.db.models.leave import LeaveLedgerEntry, LeaveType
from hozur.db.models.org import Branch, Department, Designation, Employee, Organization, Province
from hozur.db.models.requests import (
	ApprovalDefault,
	ApprovalOverride,
	ApprovalProcess,
	ApprovalProcessStep,
	CorrectionItem,
	LeaveRequest,
	MissionRequest,
	OvertimeRequest,
	Request,
	RequestApproval,
)
from hozur.db.models.rules import LaborRuleSet
from hozur.db.models.schedules import Shift, ShiftOverride, WorkPattern, WorkPatternAssignment, WorkPatternDay
from hozur.db.models.system import AppSetting, AuditEntry, Job, ReportTemplate, StoredFile

__all__ = [
	"AppSetting",
	"AppUser",
	"ApprovalDefault",
	"ApprovalOverride",
	"ApprovalProcess",
	"ApprovalProcessStep",
	"AttendanceDevice",
	"AttendancePeriod",
	"AuditEntry",
	"Branch",
	"CalendarYear",
	"CorrectionItem",
	"DailyAttendance",
	"DailyAttendanceLeave",
	"Department",
	"Designation",
	"DeviceUserMap",
	"Employee",
	"Holiday",
	"Job",
	"LaborRuleSet",
	"LeaveLedgerEntry",
	"LeaveRequest",
	"LeaveType",
	"MissionRequest",
	"Organization",
	"OvertimeRequest",
	"Province",
	"PunchImport",
	"PunchImportTemplate",
	"RawPunch",
	"ReportTemplate",
	"Request",
	"RequestApproval",
	"Shift",
	"ShiftOverride",
	"StoredFile",
	"UserRole",
	"UserSession",
	"WorkPattern",
	"WorkPatternAssignment",
	"WorkPatternDay",
]
