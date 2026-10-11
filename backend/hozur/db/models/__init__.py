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
from hozur.db.models.org import (
	Department,
	Designation,
	DesignationAssignment,
	Employee,
	Organization,
	Province,
	WorkLocation,
)
from hozur.db.models.requests import (
	ApprovalDefault,
	ApprovalDelegation,
	ApprovalOverride,
	ApprovalProcess,
	ApprovalProcessStep,
	CorrectionItem,
	LeaveRequest,
	MissionRequest,
	OvertimeRequest,
	Request,
	RequestApproval,
	RequestApprovalApprover,
	RequestSuggestion,
)
from hozur.db.models.rules import LaborRuleSet
from hozur.db.models.schedules import (
	Shift,
	ShiftOverride,
	ShiftSegment,
	WorkPattern,
	WorkPatternAssignment,
	WorkPatternDay,
)
from hozur.db.models.system import AppSetting, AuditEntry, Job, ReportTemplate, StoredFile

__all__ = [
	"AppSetting",
	"AppUser",
	"ApprovalDefault",
	"ApprovalDelegation",
	"ApprovalOverride",
	"ApprovalProcess",
	"ApprovalProcessStep",
	"AttendanceDevice",
	"AttendancePeriod",
	"AuditEntry",
	"CalendarYear",
	"CorrectionItem",
	"DailyAttendance",
	"DailyAttendanceLeave",
	"Department",
	"Designation",
	"DesignationAssignment",
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
	"RequestApprovalApprover",
	"RequestSuggestion",
	"Shift",
	"ShiftOverride",
	"ShiftSegment",
	"StoredFile",
	"UserRole",
	"UserSession",
	"WorkLocation",
	"WorkPattern",
	"WorkPatternAssignment",
	"WorkPatternDay",
]
