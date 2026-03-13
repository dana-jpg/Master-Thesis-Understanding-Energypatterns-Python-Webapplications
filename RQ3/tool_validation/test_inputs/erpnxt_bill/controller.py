# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals

import json

import frappe
from frappe import _, throw
from frappe.model.workflow import get_workflow_name, is_transition_condition_satisfied
from frappe.utils import (
	add_days,
	add_months,
	cint,
	flt,
	fmt_money,
	formatdate,
	get_last_day,
	get_link_to_form,
	getdate,
	nowdate,
	today,
)
from six import text_type

import erpnext
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
)
from erpnext.accounts.doctype.pricing_rule.utils import (
	apply_pricing_rule_for_free_items,
	apply_pricing_rule_on_transaction,
	get_applied_pricing_rules,
)
from erpnext.accounts.party import (
	get_party_account,
	get_party_account_currency,
	validate_party_frozen_disabled,
)
from erpnext.accounts.utils import get_account_currency, get_fiscal_years, validate_fiscal_year
from erpnext.buying.utils import update_last_purchase_rate
from erpnext.controllers.print_settings import (
	set_print_templates_for_item_table,
	set_print_templates_for_taxes,
)
from erpnext.controllers.sales_and_purchase_return import validate_return
from erpnext.exceptions import InvalidCurrency
from erpnext.setup.utils import get_exchange_rate
from erpnext.stock.doctype.packed_item.packed_item import make_packing_list
from erpnext.stock.get_item_details import (
	_get_item_tax_template,
	get_conversion_factor,
	get_item_details,
	get_item_tax_map,
	get_item_warehouse,
)
from erpnext.utilities.transaction_base import TransactionBase


class AccountMissingError(frappe.ValidationError): pass

force_item_fields = ("item_group", "brand", "stock_uom", "is_fixed_asset", "item_tax_rate",
	"pricing_rules", "weight_per_unit", "weight_uom", "total_weight")

class AccountsController(TransactionBase):
	def __init__(self, *args, **kwargs):
		super(AccountsController, self).__init__(*args, **kwargs)

	def get_print_settings(self):
		print_setting_fields = []
		items_field = self.meta.get_field('items')

		if items_field and items_field.fieldtype == 'Table':
			print_setting_fields += ['compact_item_print', 'print_uom_after_quantity']

		taxes_field = self.meta.get_field('taxes')
		if taxes_field and taxes_field.fieldtype == 'Table':
			print_setting_fields += ['print_taxes_with_zero_amount']

		return print_setting_fields

	@property
	def company_currency(self):
		if not hasattr(self, "__company_currency"):
			self.__company_currency = erpnext.get_company_currency(self.company)

		return self.__company_currency

	def onload(self):
		self.set_onload("make_payment_via_journal_entry",
			frappe.db.get_single_value('Accounts Settings', 'make_payment_via_journal_entry'))

		if self.is_new():
			relevant_docs = ("Quotation", "Purchase Order", "Sales Order",
							 "Purchase Invoice", "Sales Invoice")
			if self.doctype in relevant_docs:
				self.set_payment_schedule()

	def ensure_supplier_is_not_blocked(self):
		is_supplier_payment = self.doctype == 'Payment Entry' and self.party_type == 'Supplier'
		is_buying_invoice = self.doctype in ['Purchase Invoice', 'Purchase Order']
		supplier = None
		supplier_name = None

		if is_buying_invoice or is_supplier_payment:
			supplier_name = self.supplier if is_buying_invoice else self.party
			supplier = frappe.get_doc('Supplier', supplier_name)

		if supplier and supplier_name and supplier.on_hold:
			if (is_buying_invoice and supplier.hold_type in ['All', 'Invoices']) or \
					(is_supplier_payment and supplier.hold_type in ['All', 'Payments']):
				if not supplier.release_date or getdate(nowdate()) <= supplier.release_date:
					frappe.msgprint(
						_('{0} is blocked so this transaction cannot proceed').format(supplier_name), raise_exception=1)

	def validate(self):
		if not self.get('is_return'):
			self.validate_qty_is_not_zero()

		if self.get("_action") and self._action != "update_after_submit":
			self.set_missing_values(for_validate=True)

		self.ensure_supplier_is_not_blocked()

		self.validate_date_with_fiscal_year()
		self.validate_party_accounts()

		self.validate_inter_company_reference()

		self.set_incoming_rate()

		if self.meta.get_field("currency"):
			self.calculate_taxes_and_totals()

			if not self.meta.get_field("is_return") or not self.is_return:
				self.validate_value("base_grand_total", ">=", 0)

			validate_return(self)
			self.set_total_in_words()

		self.validate_all_documents_schedule()

		if self.meta.get_field("taxes_and_charges"):
			self.validate_enabled_taxes_and_charges()
			self.validate_tax_account_company()

		self.validate_party()
		self.validate_currency()

		if self.doctype == 'Purchase Invoice':
			self.calculate_paid_amount()
			# apply tax withholding only if checked and applicable
			self.set_tax_withholding()

		if self.doctype in ['Purchase Invoice', 'Sales Invoice']:
			pos_check_field = "is_pos" if self.doctype=="Sales Invoice" else "is_paid"
			if cint(self.allocate_advances_automatically) and not cint(self.get(pos_check_field)):
				self.set_advances()

			self.set_advance_gain_or_loss()

			if self.is_return:
				self.validate_qty()
			else:
				self.validate_deferred_start_and_end_date()

			self.set_inter_company_account()

		validate_regional(self)

		if self.doctype != 'Material Request':
			apply_pricing_rule_on_transaction(self)

	def on_trash(self):
		# delete sl and gl entries on deletion of transaction
		if frappe.db.get_single_value('Accounts Settings', 'delete_linked_ledger_entries'):
			frappe.db.sql("delete from `tabGL Entry` where voucher_type=%s and voucher_no=%s", (self.doctype, self.name))
			frappe.db.sql("delete from `tabStock Ledger Entry` where voucher_type=%s and voucher_no=%s", (self.doctype, self.name))

	def validate_deferred_start_and_end_date(self):
		for d in self.items:
			if d.get("enable_deferred_revenue") or d.get("enable_deferred_expense"):
				if not (d.service_start_date and d.service_end_date):
					frappe.throw(_("Row #{0}: Service Start and End Date is required for deferred accounting").format(d.idx))
				elif getdate(d.service_start_date) > getdate(d.service_end_date):
					frappe.throw(_("Row #{0}: Service Start Date cannot be greater than Service End Date").format(d.idx))
				elif getdate(self.posting_date) > getdate(d.service_end_date):
					frappe.throw(_("Row #{0}: Service End Date cannot be before Invoice Posting Date").format(d.idx))

	def validate_invoice_documents_schedule(self):
		self.validate_payment_schedule_dates()
		self.set_due_date()
		self.set_payment_schedule()
		self.validate_payment_schedule_amount()
		if not self.get('ignore_default_payment_terms_template'):
			self.validate_due_date()
		self.validate_advance_entries()

	def validate_non_invoice_documents_schedule(self):
		self.set_payment_schedule()
		self.validate_payment_schedule_dates()
		self.validate_payment_schedule_amount()

	def validate_all_documents_schedule(self):
		if self.doctype in ("Sales Invoice", "Purchase Invoice") and not self.is_return:
			self.validate_invoice_documents_schedule()
		elif self.doctype in ("Quotation", "Purchase Order", "Sales Order"):
			self.validate_non_invoice_documents_schedule()

	def before_print(self, settings=None):
		if self.doctype in ['Purchase Order', 'Sales Order', 'Sales Invoice', 'Purchase Invoice',
							'Supplier Quotation', 'Purchase Receipt', 'Delivery Note', 'Quotation']:
			if self.get("group_same_items"):
				self.group_similar_items()

			df = self.meta.get_field("discount_amount")
			if self.get("discount_amount") and hasattr(self, "taxes") and not len(self.taxes):
				df.set("print_hide", 0)
				self.discount_amount = -self.discount_amount
			else:
				df.set("print_hide", 1)

		set_print_templates_for_item_table(self, settings)
		set_print_templates_for_taxes(self, settings)

	def calculate_paid_amount(self):
		if hasattr(self, "is_pos") or hasattr(self, "is_paid"):
			is_paid = self.get("is_pos") or self.get("is_paid")

			if is_paid:
				if not self.cash_bank_account:
					# show message that the amount is not paid
					frappe.throw(_("Note: Payment Entry will not be created since 'Cash or Bank Account' was not specified"))

				if cint(self.is_return) and self.grand_total > self.paid_amount:
					self.paid_amount = flt(flt(self.grand_total), self.precision("paid_amount"))

				elif not flt(self.paid_amount) and flt(self.outstanding_amount) > 0:
					self.paid_amount = flt(flt(self.outstanding_amount), self.precision("paid_amount"))

				self.base_paid_amount = flt(self.paid_amount * self.conversion_rate,
										self.precision("base_paid_amount"))

	

	def allocate_advance_taxes(self, gl_entries):
		tax_map = self.get_tax_map()
		for pe in self.get("advances"):
			if pe.reference_type == "Payment Entry" and \
				frappe.db.get_value('Payment Entry', pe.reference_name, 'advance_tax_account'):
				pe = frappe.get_doc("Payment Entry", pe.reference_name)
				for tax in pe.get("taxes"):
					account_currency = get_account_currency(tax.account_head)

					if self.doctype == "Purchase Invoice":
						dr_or_cr = "debit" if tax.add_deduct_tax == "Add" else "credit"
						rev_dr_cr = "credit" if tax.add_deduct_tax == "Add" else "debit"
					else:
						dr_or_cr = "credit" if tax.add_deduct_tax == "Add" else "debit"
						rev_dr_cr = "debit" if tax.add_deduct_tax == "Add" else "credit"

					party = self.supplier if self.doctype == "Purchase Invoice" else self.customer
					unallocated_amount = tax.tax_amount - tax.allocated_amount
					if tax_map.get(tax.account_head):
						amount = tax_map.get(tax.account_head)
						if amount < unallocated_amount:
							unallocated_amount = amount

						gl_entries.append(
							self.get_gl_dict({
								"account": tax.account_head,
								"against": party,
								dr_or_cr: unallocated_amount,
								dr_or_cr + "_in_account_currency": unallocated_amount
								if account_currency==self.company_currency
								else unallocated_amount,
								"cost_center": tax.cost_center
							}, account_currency, item=tax))

						gl_entries.append(
							self.get_gl_dict({
								"account": pe.advance_tax_account,
								"against": party,
								rev_dr_cr: unallocated_amount,
								rev_dr_cr + "_in_account_currency": unallocated_amount
								if account_currency==self.company_currency
								else unallocated_amount,
								"cost_center": tax.cost_center
							}, account_currency, item=tax))

						frappe.db.set_value("Advance Taxes and Charges", tax.name, "allocated_amount",
							tax.allocated_amount + unallocated_amount)

						tax_map[tax.account_head] -= unallocated_amount

	def validate_multiple_billing(self, ref_dt, item_ref_dn, based_on, parentfield):
		from erpnext.controllers.status_updater import get_allowance_for
		item_allowance = {}
		global_qty_allowance, global_amount_allowance = None, None

		for item in self.get("items"):
			if item.get(item_ref_dn):
				ref_amt = flt(frappe.db.get_value(ref_dt + " Item",
					item.get(item_ref_dn), based_on), self.precision(based_on, item))
				if not ref_amt:
					frappe.msgprint(
						_("Warning: System will not check overbilling since amount for Item {0} in {1} is zero")
							.format(item.item_code, ref_dt))
				else:
					already_billed = frappe.db.sql("""
						select sum(%s)
						from `tab%s`
						where %s=%s and docstatus=1 and parent != %s
					""" % (based_on, self.doctype + " Item", item_ref_dn, '%s', '%s'),
					   (item.get(item_ref_dn), self.name))[0][0]

					total_billed_amt = flt(flt(already_billed) + flt(item.get(based_on)),
						self.precision(based_on, item))

					allowance, item_allowance, global_qty_allowance, global_amount_allowance = \
						get_allowance_for(item.item_code, item_allowance, global_qty_allowance, global_amount_allowance, "amount")

					max_allowed_amt = flt(ref_amt * (100 + allowance) / 100)

					if total_billed_amt < 0 and max_allowed_amt < 0:
						# while making debit note against purchase return entry(purchase receipt) getting overbill error
						total_billed_amt = abs(total_billed_amt)
						max_allowed_amt = abs(max_allowed_amt)

					role_allowed_to_over_bill = frappe.db.get_single_value('Accounts Settings', 'role_allowed_to_over_bill')

					if total_billed_amt - max_allowed_amt > 0.01 and role_allowed_to_over_bill not in frappe.get_roles():
						if self.doctype != "Purchase Invoice":
							self.throw_overbill_exception(item, max_allowed_amt)
						elif not cint(frappe.db.get_single_value("Buying Settings", "bill_for_rejected_quantity_in_purchase_invoice")):
							self.throw_overbill_exception(item, max_allowed_amt)

	def throw_overbill_exception(self, item, max_allowed_amt):
		frappe.throw(_("Cannot overbill for Item {0} in row {1} more than {2}. To allow over-billing, please set allowance in Accounts Settings")
			.format(item.item_code, item.idx, max_allowed_amt))

	def get_company_default(self, fieldname, ignore_validation=False):
		from erpnext.accounts.utils import get_company_default
		return get_company_default(self.company, fieldname, ignore_validation=ignore_validation)

	def get_stock_items(self):
		stock_items = []
		item_codes = list(set(item.item_code for item in self.get("items")))
		if item_codes:
			stock_items = [r[0] for r in frappe.db.sql("""
				select name from `tabItem`
				where name in (%s) and is_stock_item=1
			""" % (", ".join((["%s"] * len(item_codes))),), item_codes)]

		return stock_items

	