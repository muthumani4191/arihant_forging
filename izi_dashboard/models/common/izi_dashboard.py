# -*- coding: utf-8 -*-
# Copyright 2022 IZI PT Solusi Usaha Mudah
from odoo import api, models, fields, _
from odoo.exceptions import ValidationError
from random import randint
from bs4 import BeautifulSoup
import json
import base64

class IZIDashboardFilter(models.Model):
    _name = 'izi.dashboard.filter'
    _description = 'IZI Dashboard Filter'
    
    name = fields.Char(required=True)
    dashboard_id = fields.Many2one('izi.dashboard', string="Dashboard", required=True, ondelete='cascade')
    selection_type = fields.Selection([('single', 'Single'), ('multiple', 'Multiple')], string="Selection Type", required=True)
    source_type = fields.Selection([('model', 'Model'), ('table', 'Table'), ('predefined', 'Predefined')], string="Source Type", required=True)
    table_id = fields.Many2one('izi.table', string="Table")
    table_field_id = fields.Many2one('izi.table.field', string="Field")
    model_id = fields.Many2one('ir.model', string="Model")
    model_field_id = fields.Many2one('ir.model.fields', string="Field Model")
    model_field_values = fields.Selection([('id', 'Use ID'), ('field', 'Use Field Values')], default='field', string="Field Values")
    query_special_variable = fields.Char(string="Query Special Variable")
    value_ids = fields.Many2many('izi.dashboard.filter.value', string="Values")
    filter_analysis_ids = fields.One2many('izi.dashboard.filter.analysis', 'filter_id', string="Filter Analysis")
    
    @api.model
    def fetch_values(self, params, query=''):
        limit = params.get('limit', 10)
        text_field = params.get('textField', 'name')
        field = text_field
        model = params.get('model', False)
        table = params.get('table', False)
        db_query = params.get('dbQuery', False)
        filter_id = params.get('filterId', False)
        analysis_id = params.get('analysisId', False)
        get_table = params.get('getTable', False)
        filter = False
        field_type = False
        if filter_id:
            filter = self.env['izi.dashboard.filter'].browse(filter_id)
            if filter.table_field_id:
                field_type = filter.table_field_id.field_type
        if analysis_id:
            analysis = self.env['izi.analysis'].browse(analysis_id)
            if analysis.method == 'model':
                model = analysis.model_id.model
                params['sourceType'] = 'model'
            elif analysis.method in ('query', 'table_view'):
                db_query = analysis.db_query
            elif analysis.method == 'table':
                table = analysis.table_id.table_name or analysis.table_id.store_table_name
            if analysis.table_id:
                field_record = self.env['izi.table.field'].search([('table_id', '=', analysis.table_id.id), ('field_name', '=', field)], limit=1)
                if field_record:
                    field_type = field_record.field_type
        if not table and model:
            table = model.replace('.', '_')
        if not table and db_query:
            table = ' (%s) table_query ' % (db_query.replace(';', ''))

        res = []
        if get_table:
            if query:
                tables = self.env['izi.table'].search([('name','ilike',query)],limit=limit,order='is_template desc,name asc')
            else:
                tables = self.env['izi.table'].search([],limit=limit,order='is_template desc,name asc')
            vals = []
            for table in tables:
                vals.append({
                    'id':table.id,
                    'value':table.table_name,
                    'name':table.name,
                })
            return vals
        if params.get('sourceType') == 'model' and model:
            model_field = self.env['ir.model.fields'].search([('model_id', '=', model), ('name', '=', field)], limit=1)
            if model_field.ttype == 'many2one':
                model = model_field.relation
                table = model.replace('.', '_')
                field = 'name'
            res = self.env[model].search_read([(field, 'ilike', query)], ['id', field], limit=10)
            if model_field.ttype == 'many2one':
                for r in res:
                    if field in r:
                        r[text_field] = r[field]
            return res
        if params.get('sourceType') == 'model' and params.get('modelFieldValues') == 'id':
            self.env.cr.execute('''
                SELECT
                    id, %s
                FROM %s
                WHERE
                    %s::TEXT ILIKE '%%%s%%'
                GROUP BY id, %s
                LIMIT %s
            ''' % (text_field, table, field, query, field, limit))
            res = self.env.cr.dictfetchall()
        else:
            if field_type == 'number':
                if not query:
                    self.env.cr.execute('''
                        SELECT
                            %s
                        FROM %s
                        GROUP BY %s
                        LIMIT %s
                    ''' % (text_field, table, field, limit))
                    res = self.env.cr.dictfetchall()
                else:
                    self.env.cr.execute('''
                        SELECT
                            %s
                        FROM %s
                        WHERE
                            %s = '%s'
                        GROUP BY %s
                        LIMIT %s
                    ''' % (text_field, table, field, query, field, limit))
                    res = self.env.cr.dictfetchall()
            else:
                self.env.cr.execute('''
                    SELECT
                        %s
                    FROM %s
                    WHERE
                        %s::TEXT ILIKE '%%%s%%'
                    GROUP BY %s
                    LIMIT %s
                ''' % (text_field, table, field, query, field, limit))
                res = self.env.cr.dictfetchall()
        
        # Transform Possible JSONB Fields To String
        res = self.env['izi.analysis']._transform_json_data(res)
        return res

    def fetch_by_dashboard(self, dashboard_id):
        res = []
        filters = self.env['izi.dashboard.filter'].search([('dashboard_id', '=', dashboard_id)]) 
        for filter in filters:
            filter_vals = {
                'id': filter.id,
                'name': filter.name,
                'selection_type': filter.selection_type,
                'source_type': filter.source_type,
            } 
            values = [] 
            if filter.source_type == 'model':
                model = filter.model_id.model
                model_field_name = filter.model_field_id.name
                filter_vals['params'] = {
                    'sourceType': filter.source_type,
                    'model': model,
                    'table': model.replace('.', '_'),
                    'textField': model_field_name,
                    'fields': ['id', model_field_name],
                    'domain': [],
                    'limit': 10,
                    'modelFieldValues': filter.model_field_values,
                    'filterId': filter.id,
                }
            elif filter.source_type == 'table':
                table_field_name = filter.table_field_id.field_name
                filter_vals['params'] = {
                    'sourceType': filter.source_type,
                    'model': filter.table_id.model_id.model,
                    'table': filter.table_id.table_name,
                    'dbQuery': filter.table_id.db_query,
                    'textField': table_field_name,
                    'fields': ['id', table_field_name],
                    'domain': [],
                    'limit': 10,
                    'modelFieldValues': 'field',
                    'filterId': filter.id,
                }
            elif filter.source_type == 'predefined':
                for filter_value in filter.value_ids:
                    values.append({
                        'name': filter_value.name,
                        'value': filter_value.value or filter_value.name,
                        'id': filter_value.value or filter_value.name,
                    })
            filter_vals['values'] = values
            res.append(filter_vals)
        return res

class IZIDashboardFilterValue(models.Model):
    _name = 'izi.dashboard.filter.value'
    _description = 'IZI Dashboard Filter Value'
    
    filter_id = fields.Many2one('izi.dashboard.filter', string="Filter")
    name = fields.Char(string="Name")
    value = fields.Char(string="Value")

class IZIDashboardFilterAnalysis(models.Model):
    _name = 'izi.dashboard.filter.analysis'
    _description = 'IZI Dashboard Filter Analysis'
    
    name = fields.Char(string="Name")
    
    filter_id = fields.Many2one('izi.dashboard.filter', string="Filter", required=True, ondelete='cascade')
    dashboard_id = fields.Many2one('izi.dashboard', related='filter_id.dashboard_id')
    table_id = fields.Many2one('izi.table', string="Table", required=False, ondelete='cascade')
    allowed_analysis_ids = fields.One2many('izi.analysis', related='table_id.analysis_ids', string='Allowed Analysis')
    analysis_id = fields.Many2one('izi.analysis', string="Analysis", required=False, ondelete='cascade')
    allowed_field_ids = fields.One2many('izi.table.field', string="Analysis Fields", related='table_id.field_ids')
    field_id = fields.Many2one('izi.table.field', string="Field", required=False)
    operator = fields.Selection([('=', '='), ('!=', '!='), ('>', '>'), ('>=', '>='), ('<', '<'), ('<=', '<='), ('like', 'like'), ('ilike', 'ilike'), ('in', 'in'), ('not in', 'not in')], default='=', string="Operator", required=True)

class IZIAnalysis(models.Model):
    _inherit = 'izi.analysis'
    
    filter_analysis_ids = fields.One2many('izi.dashboard.filter.analysis', 'analysis_id', string="Filter Analysis")

class IZIDashboard(models.Model):
    _name = 'izi.dashboard'
    _description = 'IZI Dashboard'
    _order = 'sequence,id'

    def _default_theme(self):
        default_theme = False
        try:
            default_theme = self.env.ref('izi_dashboard.izi_dashboard_theme_contrast').id
        except Exception as e:
            pass
        return default_theme

    name = fields.Char('Name', required=True)
    block_ids = fields.One2many(comodel_name='izi.dashboard.block',
                                inverse_name='dashboard_id', string='Dashboard Blocks')
    theme_id = fields.Many2one(comodel_name='izi.dashboard.theme', string='Theme', default=_default_theme)
    theme_name = fields.Char(related='theme_id.name', string='Theme Name')
    animation = fields.Boolean('Enable Animation', default=True)
    group_ids = fields.Many2many(comodel_name='res.groups', string='Groups')
    new_block_position = fields.Selection([
        ('top', 'Top'),
        ('bottom', 'Bottom'),
    ], default='top', string='New Chart Position', required=True)
    sequence = fields.Integer(string='Sequence')
    date_format = fields.Selection([
        ('today', 'Today'),
        ('this_week', 'This Week'),
        ('this_month', 'This Month'),
        ('this_year', 'This Year'),
        ('mtd', 'Month to Date'),
        ('ytd', 'Year to Date'),
        ('last_week', 'Last Week'),
        ('last_month', 'Last Month'),
        ('last_two_months', 'Last 2 Months'),
        ('last_three_months', 'Last 3 Months'),
        ('last_year', 'Last Year'),
        ('last_10', 'Last 10 Days'),
        ('last_30', 'Last 30 Days'),
        ('last_60', 'Last 60 Days'),
        ('custom', 'Custom Range'),
    ], default=False, string='Date Filter')
    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    menu_ids = fields.One2many('ir.ui.menu', 'dashboard_id', string='Menus')
    refresh_interval = fields.Integer('Refresh Interval in Seconds')
    filter_ids = fields.One2many('izi.dashboard.filter', 'dashboard_id', string="Filters")
    analysis_ids = fields.Many2many('izi.analysis', 'izi_dashboard_block', 'dashboard_id', 'analysis_id', string='Analysis')
    rtl = fields.Boolean('RTL (Right to Left)', default=False)
    lang_id = fields.Many2one('res.lang', string='Language')
    table_id = fields.Many2one('izi.table', 'Table')
    table_name = fields.Char(related='table_id.name', string='Table Name')
    table_field_names = fields.Char('Table Field Names', compute='_compute_field_names')

    # SLIDE FIELDS ------------
    slide_ids = fields.One2many('izi.dashboard.slide', 'dashboard_id', string='Slide')
    general_bg_file = fields.Binary('Background', required=False, attachment=True)
    general_bg_filename = fields.Char('Background Name', required=False)
    transition = fields.Selection([
        ('none', 'None'),
        ('fade', 'Fade'),
        ('slide', 'Slide'),
        ('convex', 'Convex'),
        ('concave', 'Concave'),
        ('zoom', 'Zoom'),
    ], string='Transition', required=True, default="none")
    theme = fields.Selection([
        ('black','Black'),
        ('white','White'),
        ('league','League'),
        ('beige','Beige'),
        ('night','Night'),
        ('serif','Serif'),
        ('simple','Simple'),
        ('solarized','Solarized'),
        ('moon','Moon'),
        ('dracula','Dracula'),
        ('sky','Sky'),
        ('blood','Blood'),
    ], string='Theme', required=True, default='white')
    is_repeat = fields.Boolean('Repeat Slide', default=False)
    auto_slide = fields.Integer('Auto Slide (Seconds)', default=0)

    def _compute_field_names(self):
        for rec in self:
            table_field_names = ''
            if rec.table_id:
                for field in rec.table_id.field_ids:
                    table_field_names += field.field_name + ', '
            rec.table_field_names = table_field_names

    @api.model
    def get_user_groups(self):
        manager_dashboard = self.env.ref('izi_dashboard.group_manager_dashboard')
        manager_analysis = self.env.ref('izi_data.group_manager_analysis')
        user_groups = self.env.user.groups_id
        user_dashboard = {
            'user_group_dashboard': 'Manager' if manager_dashboard.id in user_groups.ids else 'User',
            'user_group_analysis': 'Manager' if manager_analysis.id in user_groups.ids else 'User'
        }
        return user_dashboard

    def write(self, vals):
        if vals.get('refresh_interval', False) and vals.get('refresh_interval') < 10:
            raise ValidationError('Refresh interval have to be more than 10 seconds')
        res = super(IZIDashboard, self).write(vals)
        return res
    
    def action_save_and_close(self):
        return True

    def action_duplicate(self):
        self.ensure_one()
        dashboards = self.search([('name', 'like', self.name)])
        new_identifier = str(len(dashboards) + 1)
        self.copy({
            'name': '%s %s' % (self.name, new_identifier),
        })

    def update_dashboard_table(self, table_id):
        self.table_id = table_id

    def action_open_slide(self):
        url = f"izi/dashboard/slide/{self.id}"
        res = self.action_check_key()
        if res['status'] == 401:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Need API Access'),
                'target': 'new',
                'res_model': 'izi.lab.api.key.wizard',
                'views': [[False, 'form']],
                'context': {},
            }
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def export_all_config(self):
        data = []
        for analysis in self.analysis_ids:
            vals = analysis._prepare_export_vals()
            data.append(vals)
        
        json_data = json.dumps(data)
        json_data_bytes = json_data.encode('utf-8')
        json_data_base64 = base64.b64encode(json_data_bytes)
        
        attachment = {
            'name': f'{self.name} Config.json',
            'datas': json_data_base64,
            'res_model': self._name,
            'res_id': self.id,
            'type': 'binary',
        }
        
        attachment_id = self.env['ir.attachment'].create(attachment)
        return attachment_id.id

class IziDashboardSlide(models.Model):
    _name = 'izi.dashboard.slide'
    _description = 'IZI Dashboard Slide'

    dashboard_id = fields.Many2one('izi.dashboard', string='Dashboard')
    slide_name = fields.Char('Slide Name')
    slide_title = fields.Char('Slide Title')
    sequence = fields.Integer(string='Sequence')
    analysis_id = fields.Many2one('izi.analysis', string='Analysis', domain="[('id', 'in', analysis_domain)]")
    analysis_domain = fields.Many2many('izi.analysis', compute='_onchange_dashboard_id', store=False)

    layout = fields.Selection([
        ('title', 'Title Slide'),
        ('column', 'Two Columns'),
        ('row', 'Two Rows'),
        ('text', 'Text Only'),
        ('chart', 'Chart Only'),
    ], string='Layout', required=True, default='title')
    chart_size = fields.Integer('Chart Size (%)',default=50)
    text_size = fields.Integer('Text Size (%)',default=50)
    text_content = fields.Text('Text Content')
    text_align = fields.Selection([
        ('left', 'Left'),
        ('center', 'Center'),
        ('right', 'Right'),
        ('justify', 'Justify'),
    ], string='Text Align', required=True, default='left')
    automatic_font_size = fields.Boolean('Automatic Font Size',default=True, help='Best for short texts')
    font_size = fields.Integer('Font Size',default=31)
    automatic_font_color = fields.Boolean('Automatic Font Color',default=True, help='Automatically follow selected themes')
    font_color = fields.Char('Font Color',default='black')
    bg_file = fields.Binary('Background', required=False, attachment=True)
    bg_filename = fields.Char('Background Name', required=False)
    layout_order = fields.Selection([
        ('text_chart', 'Text -> Chart'),
        ('chart_text', 'Chart -> Text'),
    ], string='Layout Order', required=True, default="text_chart")
    show_logo = fields.Boolean('Show Logo')

    @api.onchange('chart_size')
    def _onchange_chart_size(self):
        for rec in self:
            rec.text_size = 100 - rec.chart_size
    
    @api.onchange('dashboard_id')
    def _onchange_dashboard_id(self):
        for record in self:
            if record.dashboard_id:
                record.analysis_domain = record.dashboard_id.analysis_ids.ids
            else:
                record.analysis_domain = []
    
    @api.constrains('analysis_id')
    def _constrains_analysis_id(self):
        for record in self:
            dashboard = self.env['izi.dashboard'].browse(record.dashboard_id.id)
            slides = dashboard.slide_ids.filtered(lambda s: s.id != record.id)  # Exclude the current record

            if record.analysis_id:
                for slide in slides:
                    if slide.analysis_id.id == record.analysis_id.id:
                        raise ValidationError(_('Cannot have multiple slides using the same analysis!'))
    
    def action_generate_content_ai(self):
        data = self.analysis_id.try_get_analysis_data_dashboard()
        result = self.analysis_id.with_context(is_short=True).action_get_lab_description(ai_analysis_data = data, dashboard_id = self.dashboard_id.id)
        if result['status'] == 401:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Need API Access'),
                'target': 'new',
                'res_model': 'izi.lab.api.key.wizard',
                'views': [[False, 'form']],
                'context': {},
            }
        ai_analysis_text = result.get('ai_analysis_text', '')
        clean_text = self.clean_html_tags(ai_analysis_text)
        self.text_content = clean_text
        return {
            'type': 'ir.actions.act_window',
            'name': 'Slides',
            'target': 'new',
            'res_id': self.id,
            'res_model': 'izi.dashboard.slide',
            'views': [[False, 'form']],
        }

    def clean_html_tags(self,html_text):
        soup = BeautifulSoup(html_text, "html.parser")
        return soup.get_text()

    def action_save_only(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Dashboard',
            'target': 'new',
            'res_id': self.dashboard_id.id,
            'res_model': 'izi.dashboard',
            'views': [[False, 'form']],
        }

class IrMenu(models.Model):
    _inherit = 'ir.ui.menu'

    dashboard_id = fields.Many2one('izi.dashboard', string='Dashboard')
    
    @api.model
    def create(self, vals):
        rec = super(IrMenu, self).create(vals)
        if rec.dashboard_id:
            action = self.env['ir.actions.act_window'].create({
                'res_model': 'izi.dashboard',
                'target': 'current',
                'view_mode': 'izidashboard',
                'context': '''{'dashboard_id': %s}''' % (rec.dashboard_id.id)
            })
            rec.action = 'ir.actions.act_window,%s' % action.id
        return rec