# -*- coding: utf-8 -*-
# Copyright 2012, Israel Cruz Argil, Argil Consulting
# Copyright 2016, Jarsa Sistemas, S.A. de C.V.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from __future__ import division

from openerp import _, api, fields, models
from openerp.exceptions import ValidationError

import logging
_logger = logging.getLogger(__name__)
try:
    from num2words import num2words
except ImportError:
    _logger.debug('Cannot `import num2words`.')


class FleetVehicleLogFuel(models.Model):
    _name = 'fleet.vehicle.log.fuel'
    _inherit = ['fleet.vehicle.log.fuel', 'mail.thread', 'ir.needaction_mixin']
    _order = "date desc,vehicle_id desc"

    name = fields.Char()
    travel_id = fields.Many2one(
        'tms.travel',
        string='Travel',)
    expense_id = fields.Many2one(
        'tms.expense',
        string='Expense',)
    employee_id = fields.Many2one(
        'hr.employee',
        string='Driver',
        domain=[('driver', '=', True)],
        compute='_compute_employee_id',
        store=True,)
    odometer = fields.Float(related='vehicle_id.odometer',)
    product_uom_id = fields.Many2one(
        'product.uom',
        string='UoM ')
    product_qty = fields.Float(
        string='Liters',
        required=True,
        default=1.0,)
    tax_amount = fields.Float(
        string='Taxes',
        required=True,)
    price_total = fields.Float(
        string='Total',
        required=True,)
    special_tax_amount = fields.Float(
        compute="_compute_special_tax_amount",
        string='IEPS',)
    price_unit = fields.Float(
        compute='_compute_price_unit',
        string='Unit Price',)
    price_subtotal = fields.Float(
        string="Subtotal",
        compute='_compute_price_subtotal',)
    invoice_id = fields.Many2one(
        'account.invoice',
        'Invoice',
        readonly=True,
        domain=[('state', '!=', 'cancel')],)
    invoice_paid = fields.Boolean(
        string='Invoice Paid',
        compute='_compute_invoiced_paid')
    operating_unit_id = fields.Many2one(
        'operating.unit',
        string='Operating Unit',)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        required=True,
        default=lambda self: self.env.user.company_id.currency_id,)
    notes = fields.Char()
    state = fields.Selection(
        [('draft', 'Draft'),
         ('approved', 'Approved'),
         ('confirmed', 'Confirmed'),
         ('closed', 'Closed'),
         ('cancel', 'Cancelled')],
        string='State',
        readonly=True,
        default='draft',)
    no_travel = fields.Boolean(
        string='No Travel',
        help="Check this if you want to create Fuel Voucher "
        "with no Travel.",)
    vendor_id = fields.Many2one(
        'res.partner',
        required=True)
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain=[('tms_product_category', '=', 'fuel')])
    currency_id = fields.Many2one(
        'res.currency', 'Currency', required=True,
        default=lambda self: self.env.user.company_id.currency_id)
    expense_control = fields.Boolean(
        readonly=True,
    )
    ticket_number = fields.Char(
        string='Ticket Number',)

    @api.multi
    @api.depends('vehicle_id')
    def _compute_employee_id(self):
        for rec in self:
            rec.employee_id = rec.vehicle_id.employee_id.id

    @api.multi
    @api.depends('tax_amount')
    def _compute_price_subtotal(self):
        for rec in self:
            rec.price_subtotal = 0
            if rec.tax_amount > 0:
                rec.price_subtotal = rec.tax_amount / 0.16

    @api.multi
    @api.depends('product_qty', 'price_subtotal')
    def _compute_price_unit(self):
        for rec in self:
            rec.price_unit = 0
            if rec.product_qty and rec.price_subtotal > 0:
                rec.price_unit = rec.price_subtotal / rec.product_qty

    @api.multi
    @api.depends('price_subtotal', 'tax_amount', 'price_total')
    def _compute_special_tax_amount(self):
        for rec in self:
            rec.special_tax_amount = 0
            if rec.price_subtotal and rec.price_total and rec.tax_amount > 0:
                rec.special_tax_amount = (
                    rec.price_total - rec.price_subtotal - rec.tax_amount)

    @api.multi
    def action_approved(self):
        for rec in self:
            message = _('<b>Fuel Voucher Approved.</b></br><ul>'
                        '<li><b>Approved by: </b>%s</li>'
                        '<li><b>Approved at: </b>%s</li>'
                        '</ul>') % (self.env.user.name, fields.Date.today())
            rec.message_post(body=message)
            rec.state = 'approved'

    @api.multi
    def action_cancel(self):
        for rec in self:
            if rec.invoice_id:
                raise ValidationError(
                    _('Could not cancel Fuel Voucher !'),
                    _('This Fuel Voucher is already Invoiced'))
            elif (rec.travel_id and
                  rec.travel_id.state == 'closed'):
                raise ValidationError(
                    _('Could not cancel Fuel Voucher !'
                        'This Fuel Voucher is already linked to Travel '
                        'Expenses record'))

    @api.model
    def create(self, values):
        res = super(FleetVehicleLogFuel, self).create(values)
        if not res.operating_unit_id.fuel_log_sequence_id:
            raise ValidationError(_(
                'You need to define the sequence for fuel logs in base %s' %
                res.operating_unit_id.name
            ))
        sequence = res.operating_unit_id.fuel_log_sequence_id
        res.name = sequence.next_by_id()
        return res

    @api.multi
    def set_2_draft(self):
        for rec in self:
            message = _(
                '<b>Fuel Voucher Draft.</b></br><ul>'
                '<li><b>Drafted by: </b>%s</li>'
                '<li><b>Drafted at: </b>%s</li>'
                '</ul>') % (self.env.user.name, fields.Date.today())
            rec.message_post(body=message)
            rec.state = 'draft'

    @api.multi
    def action_confirm(self):
        for rec in self:
            if (rec.product_qty <= 0 or
                    rec.tax_amount <= 0 or
                    rec.price_total <= 0):
                raise ValidationError(
                    _('Liters, Taxes and Total'
                      ' must be greater than zero.'))
            message = _(
                '<b>Fuel Voucher Confirmed.</b></br><ul>'
                '<li><b>Confirmed by: </b>%s</li>'
                '<li><b>Confirmed at: </b>%s</li>'
                '</ul>') % (self.env.user.name, fields.Date.today())
            rec.message_post(body=message)
            rec.state = 'confirmed'

    @api.onchange('travel_id')
    def _onchange_travel(self):
        self.vehicle_id = self.travel_id.unit_id
        self.employee_id = self.travel_id.employee_id

    @api.depends('invoice_id')
    def _compute_invoiced_paid(self):
        for rec in self:
            rec.invoice_paid = (
                rec.invoice_id.id and
                rec.invoice_id.state == 'paid')

    @api.onchange('no_travel')
    def _onchange_no_tracel(self):
        if self.no_travel:
            self.travel_id = False
            self.vehicle_id = False

    @api.multi
    def _amount_to_text(self, product_qty):
        total = str(float(product_qty)).split('.')[0]
        total = num2words(float(total), lang='es').upper()
        return '%s' % (total)
