# -*- coding: utf-8 -*-
import datetime
import io
import json
import operator
import re

from odoo import http, exceptions
from odoo.tools import pycompat
from odoo.tools.misc import xlwt
from odoo.tools.translate import _
from odoo.exceptions import UserError
from odoo.http import serialize_exception, request
from odoo.addons.web.controllers.main import ExportFormat, content_disposition

# 导出EXCLE的基类


class ExcelExportBase(ExportFormat, http.Controller):
    # Excel needs raw data to correctly handle numbers and date values
    raw_data = True
    default_widths = 8000
    widths = {"策略号": 1800,
              "贷方金额": 3000,
              "分录摘要": 10000,
              "附件张数": 2000,
              "核算机构": 8000,
              "核算机构编码": 4000,
              "核算机构名称": 8000,
              "核算类别": 6000,
              "会计科目和核算统计项目": 15000,
              "核算项目编码": 4000,
              "核算项目类别": 4000,
              "核算项目名称": 12000,
              "会计科目": 10000,
              "记账日期": 3000,
              "借方金额": 3000,
              "科目编码": 3500,
              "科目类别": 2500,
              "科目名称": 10000,
              "末级科目": 2500,
              "凭证的标签": 4000,
              "凭证号": 1800,
              "凭证来源": 2000,
              "凭证中可选": 3000,
              "全局标签": 8000,
              "审核人": 3000,
              "所属机构": 8000,
              "所属科目体系": 3500,
              "所属凭证": 2500,
              "唯一编号": 2500,
              "现金流量": 15000,
              "业务日期": 4000,
              "余额方向": 2500,
              "制单人": 3000}

    def index_base(self, data, token, listType):
        self.listType = listType
        params = json.loads(data)
        model, fields, ids, domain = \
            operator.itemgetter('model', 'fields', 'ids',
                                'domain')(params)
        # 表头
        columns_headers = self.listType.get_colums_headers(fields)
        self.column_count = len(columns_headers)
        Model = request.env[model].sudo().with_context(
            **params.get('context', {}))
        Model = request.env[model].with_context(**params.get('context', {}))
        records = Model.browse(ids) or Model.search(
            domain, offset=0, limit=False, order=False)
        self.row_count = len(records)
        # 表体
        export_data = self.listType.get_export_data(records)
        response_data = self.from_data(columns_headers, export_data)
        return request.make_response(response_data,
                                     headers=[('Content-Disposition',
                                               content_disposition(self.filename(Model._description))),
                                              ('Content-Type', self.content_type)],
                                     cookies={'fileToken': token})

    @property
    def content_type(self):
        return 'application/vnd.ms-excel'

    def filename(self, base):
        return base + '.xls'

    def from_data(self, fields, rows):
        if len(rows) > 65535:
            raise UserError(
                _('导出的行数过多 (%s 行, 上限为: 65535行) , 请分多次导出') % len(rows))

        workbook = xlwt.Workbook()
        worksheet = workbook.add_sheet('Sheet 1')
        header_style = xlwt.easyxf(
            'font:bold True;align: vert center, horiz center;')
        for i, fieldname in enumerate(fields):
            worksheet.write(0, i, fieldname, header_style)
            worksheet.col(i).width = self.setColumnWidth(
                fieldname)  # around 220 pixels

        base_style = xlwt.easyxf('align: wrap yes')
        date_style = xlwt.easyxf(
            'align: wrap yes', num_format_str='YYYY-MM-DD')
        datetime_style = xlwt.easyxf(
            'align: wrap yes', num_format_str='YYYY-MM-DD HH:mm:SS')

        for row_index, row in enumerate(rows):
            for cell_index, cell_value in enumerate(row):
                cell_style = base_style
                if isinstance(cell_value, bytes) and not isinstance(cell_value, pycompat.string_types):
                    try:
                        cell_value = pycompat.to_text(cell_value)
                    except UnicodeDecodeError:
                        raise UserError(
                            _("Binary fields can not be exported to Excel unless their content is base64-encoded. That does not seem to be the case for %s.") % fields[cell_index])

                if isinstance(cell_value, pycompat.string_types):
                    cell_value = re.sub(
                        "\r", " ", pycompat.to_text(cell_value))
                    # Excel supports a maximum of 32767 characters in each cell:
                    cell_value = cell_value[:32767]
                elif isinstance(cell_value, datetime.datetime):
                    cell_style = datetime_style
                elif isinstance(cell_value, datetime.date):
                    cell_style = date_style
                worksheet.write(row_index + 1, cell_index,
                                cell_value, cell_style)

        fp = io.BytesIO()
        workbook.save(fp)
        fp.seek(0)
        data = fp.read()
        fp.close()
        return data

    def setColumnWidth(self, fieldname):
        return ExcelExportBase.widths.get(fieldname, ExcelExportBase.default_widths)

    @http.route('/web/export/accountcore.voucher', type='http', auth="user")
    # @serialize_exception
    def accountcore_voucher(self, data, token):
        listType = ExcelExportVouchers()
        return self.index_base(data, token, listType)

    @http.route('/web/export/accountcore.entry', type='http', auth="user")
    # @serialize_exception
    def accountcore_entry(self, data, token):
        listType = ExcelExportEntrys()
        return self.index_base(data, token, listType)

    @http.route('/web/export/accountcore.account', type='http', auth="user")
    # @serialize_exception
    def accountcore_account(self, data, token):
        listType = ExcelExportAccounts()
        return self.index_base(data, token, listType)

    @http.route('/web/export/accountcore.item', type='http', auth="user")
    # @serialize_exception
    def accountcore_item(self, data, token):
        listType = ExcelExportItems()
        return self.index_base(data, token, listType)

    @http.route('/web/export/accountcore.org', type='http', auth="user")
    # @serialize_exception
    def accountcore_org(self, data, token):
        listType = ExcelExportOrgs()
        return self.index_base(data, token, listType)

# 凭证列表导出EXCEL


class ExcelExportVouchers():
    def get_colums_headers(self, fields):
        columns_headers = ['记账日期',
                           '核算机构',
                           '分录摘要',
                           '科目编码',
                           '会计科目和核算统计项目',
                           '借方金额',
                           '贷方金额',
                           '现金流量',
                           '凭证号',
                           '唯一编号',
                           '制单人',
                           '审核人',
                           '全局标签',
                           '凭证来源',
                           '凭证的标签',
                           '策略号',
                           '附件张数']
        return columns_headers

    def get_export_data(self, records):
        export_data = []
        vouchers = records
        for v in vouchers:
            glob_tags = [g.name for g in v.glob_tag]
            glot_tags_str = '/'.join(glob_tags)
            voucher_before_entry = [v.voucherdate, v.org.name]
            v_after_entry = [v.v_number,
                             v.uniqueNumber,
                             v.createUser.name,
                             v.reviewer.name,
                             glot_tags_str,
                             v.soucre.name,
                             re.sub(r'<br>|<p>|</p>', '', v.roolbook_html),
                             v.number,
                             v.appendixCount]
            entrys = v.entrys
            for e in entrys:
                items_html = re.sub(r'<br>|<p>|</p>', '', e.items_html)
                entry = [e.explain, e.account.number, items_html, e.damount, e.camount, e.cashFlow.name]
                entry_line = []
                entry_line.extend(voucher_before_entry)
                entry_line.extend(entry)
                entry_line.extend(v_after_entry)
                export_data.append(entry_line)
        return export_data


# 分录列表导出EXCEL


class ExcelExportEntrys():
    def get_colums_headers(self, fields):
        columns_headers = ['记账日期',
                           '核算机构',
                           '分录摘要',
                           '科目编码',
                           '会计科目和核算统计项目',
                           '借方金额',
                           '贷方金额',
                           '现金流量项目',
                           '凭证号',
                           '所属凭证',
                           '全局标签',
                           '业务日期']
        return columns_headers

    def get_export_data(self, records):
        export_data = []
        entry = records
        for e in entry:
            glob_tags = [g.name for g in e.glob_tag]
            glot_tags_str = '/'.join(glob_tags)
            items_html = re.sub(r'<br>|<p>|</p>', '', e.items_html)
            entry_line = [e.v_voucherdate,
                          e.org.name,
                          e.explain,
                          e.account.number,
                          items_html,
                          e.damount,
                          e.camount,
                          e.cashFlow.name,
                          e.v_number,
                          e.voucher.name,
                          glot_tags_str,
                          e.v_real_date]
            export_data.append(entry_line)
        return export_data

# 会计科目列表导出EXCEL


class ExcelExportAccounts():
    def get_colums_headers(self, fields):
        columns_headers = ["所属机构",
                            "所属科目体系",
                            "科目类别",
                            "科目编码",	
                            "科目名称",	
                            "核算类别",	
                            "余额方向",	
                            "凭证中可选",	
                            "末级科目",	
                            "全局标签"]
        return columns_headers

    def get_export_data(self, records):
        export_data = []
        lines = records
        for line in lines:
            glob_tags = [g.name for g in line.glob_tag]
            glob_tags_str = '/'.join(glob_tags)
            orgs = [o.name for o in line.org]
            orgs_str = '/'.join(orgs)
            direction = "借"
            if line.direction == "-1":
                direction = "贷"
            excel_line = [orgs_str,
                          line.accountsArch.name,
                          line.accountClass.name,
                          line.number,
                          line.name,
                          line.itemClassesHtml,
                          direction,
                          line.is_show,
                          line.is_last,
                          glob_tags_str]
            export_data.append(excel_line)
            export_data.sort(key=lambda e: e[3])
        return export_data

# 核算项目列表导出EXCEL


class ExcelExportItems():
    def get_colums_headers(self, fields):
        columns_headers = ["所属机构",	
                            "核算项目类别",	
                            "核算项目编码",	
                            "核算项目名称",	
                            "唯一编号",	
                            "全局标签"]

        return columns_headers

    def get_export_data(self, records):
        export_data = []
        lines = records
        for line in lines:
            glob_tags = [g.name for g in line.glob_tag]
            glob_tags_str = '/'.join(glob_tags)
            orgs = [o.name for o in line.org]
            orgs_str = '/'.join(orgs)
            excel_line = [orgs_str,
                          line.item_class_name,
                          line.number,
                          line.name,
                          line.uniqueNumber,
                          glob_tags_str]
            export_data.append(excel_line)
            export_data.sort(key=lambda e: e[1])
        return export_data

# 核算项目列表导出EXCEL


class ExcelExportOrgs():
    def get_colums_headers(self, fields):
        columns_headers = ["核算机构编码",
                            "核算机构名称",
                            "全局标签"]
        return columns_headers

    def get_export_data(self, records):
        export_data = []
        lines = records
        for line in lines:
            glob_tags = [g.name for g in line.glob_tag]
            glob_tags_str = '/'.join(glob_tags)
            excel_line = [line.number,
                          line.name,
                          glob_tags_str]
            export_data.append(excel_line)
        return export_data
