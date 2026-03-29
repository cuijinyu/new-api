"""
Gemini 渠道质量测试报告生成脚本
生成时间: 2026-03-28
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import datetime, os

# ── 注册中文字体 ──────────────────────────────────────────────
pdfmetrics.registerFont(TTFont('SimHei', 'C:/Windows/Fonts/simhei.ttf'))
pdfmetrics.registerFont(TTFont('MSYH',   'C:/Windows/Fonts/msyh.ttc',  subfontIndex=0))
pdfmetrics.registerFont(TTFont('MSYHBd', 'C:/Windows/Fonts/msyhbd.ttc', subfontIndex=0))

# ── 颜色定义 ─────────────────────────────────────────────────
C_DARK_BLUE   = colors.HexColor('#1a2744')
C_MID_BLUE    = colors.HexColor('#2563eb')
C_LIGHT_BLUE  = colors.HexColor('#dbeafe')
C_ACCENT      = colors.HexColor('#0ea5e9')
C_GREEN       = colors.HexColor('#16a34a')
C_RED         = colors.HexColor('#dc2626')
C_ORANGE      = colors.HexColor('#ea580c')
C_GRAY_BG     = colors.HexColor('#f8fafc')
C_GRAY_BORDER = colors.HexColor('#e2e8f0')
C_TEXT        = colors.HexColor('#1e293b')
C_SUBTEXT     = colors.HexColor('#64748b')
C_WHITE       = colors.white
C_YELLOW_BG   = colors.HexColor('#fefce8')

# ── 样式定义 ─────────────────────────────────────────────────
def make_styles():
    s = {}
    base = dict(fontName='MSYH', textColor=C_TEXT, leading=16)

    s['title'] = ParagraphStyle('title',
        fontName='MSYHBd', fontSize=24, textColor=C_WHITE,
        leading=32, alignment=TA_CENTER, spaceAfter=6)

    s['subtitle'] = ParagraphStyle('subtitle',
        fontName='MSYH', fontSize=11, textColor=colors.HexColor('#bfdbfe'),
        leading=16, alignment=TA_CENTER)

    s['h1'] = ParagraphStyle('h1',
        fontName='MSYHBd', fontSize=14, textColor=C_DARK_BLUE,
        leading=20, spaceBefore=18, spaceAfter=8,
        borderPad=(0,0,4,0))

    s['h2'] = ParagraphStyle('h2',
        fontName='MSYHBd', fontSize=11, textColor=C_MID_BLUE,
        leading=16, spaceBefore=12, spaceAfter=6)

    s['body'] = ParagraphStyle('body',
        fontName='MSYH', fontSize=9.5, textColor=C_TEXT,
        leading=15, spaceAfter=4)

    s['small'] = ParagraphStyle('small',
        fontName='MSYH', fontSize=8.5, textColor=C_SUBTEXT,
        leading=13)

    s['note'] = ParagraphStyle('note',
        fontName='MSYH', fontSize=8.5, textColor=colors.HexColor('#92400e'),
        leading=13, leftIndent=8)

    s['ok']   = ParagraphStyle('ok',   fontName='MSYHBd', fontSize=9, textColor=C_GREEN,  leading=14, alignment=TA_CENTER)
    s['fail'] = ParagraphStyle('fail', fontName='MSYHBd', fontSize=9, textColor=C_RED,    leading=14, alignment=TA_CENTER)
    s['warn'] = ParagraphStyle('warn', fontName='MSYHBd', fontSize=9, textColor=C_ORANGE, leading=14, alignment=TA_CENTER)

    s['th']   = ParagraphStyle('th', fontName='MSYHBd', fontSize=9,   textColor=C_WHITE,   leading=13, alignment=TA_CENTER)
    s['td']   = ParagraphStyle('td', fontName='MSYH',   fontSize=8.5, textColor=C_TEXT,    leading=13, alignment=TA_CENTER)
    s['td_l'] = ParagraphStyle('td_l',fontName='MSYH',  fontSize=8.5, textColor=C_TEXT,    leading=13, alignment=TA_LEFT)
    s['td_b'] = ParagraphStyle('td_b',fontName='MSYHBd',fontSize=8.5, textColor=C_TEXT,    leading=13, alignment=TA_CENTER)
    s['code'] = ParagraphStyle('code', fontName='SimHei', fontSize=8, textColor=colors.HexColor('#1e40af'), leading=12)

    return s

S = make_styles()

# ── 辅助函数 ─────────────────────────────────────────────────
def p(text, style='body'): return Paragraph(text, S[style])
def sp(h=0.3): return Spacer(1, h*cm)
def hr(): return HRFlowable(width='100%', thickness=0.5, color=C_GRAY_BORDER, spaceAfter=6, spaceBefore=4)

def section_title(text, number):
    return Table(
        [[Paragraph(f'{number}', ParagraphStyle('sn', fontName='MSYHBd', fontSize=11,
            textColor=C_WHITE, alignment=TA_CENTER, leading=14)),
          Paragraph(text, ParagraphStyle('st', fontName='MSYHBd', fontSize=12,
            textColor=C_DARK_BLUE, leading=16))]],
        colWidths=[0.7*cm, 15.3*cm],
        style=TableStyle([
            ('BACKGROUND', (0,0), (0,0), C_MID_BLUE),
            ('BACKGROUND', (1,0), (1,0), C_LIGHT_BLUE),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (0,0), 4),
            ('LEFTPADDING', (1,0), (1,0), 10),
            ('ROUNDEDCORNERS', [3,3,3,3]),
        ])
    )

def make_table(headers, rows, col_widths, zebra=True):
    header_row = [Paragraph(h, S['th']) for h in headers]
    data = [header_row]
    for i, row in enumerate(rows):
        cells = []
        for j, cell in enumerate(row):
            if isinstance(cell, str):
                cells.append(Paragraph(cell, S['td']))
            else:
                cells.append(cell)
        data.append(cells)

    style_cmds = [
        ('BACKGROUND', (0,0), (-1,0), C_DARK_BLUE),
        ('TEXTCOLOR', (0,0), (-1,0), C_WHITE),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.4, C_GRAY_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [C_WHITE, C_GRAY_BG] if zebra else [C_WHITE]),
    ]
    return Table(data, colWidths=col_widths, style=TableStyle(style_cmds), repeatRows=1)

def status_cell(ok):
    if ok == 'ok':   return Paragraph('✓ 可用', S['ok'])
    if ok == 'fail': return Paragraph('✗ 不可用', S['fail'])
    if ok == 'warn': return Paragraph('⚠ 注意', S['warn'])
    return Paragraph(ok, S['td'])

def rating_bar(score, max_score=5):
    filled = '●' * score
    empty  = '○' * (max_score - score)
    if score >= 4:
        hex_color = '#16a34a'
    elif score >= 3:
        hex_color = '#ea580c'
    else:
        hex_color = '#dc2626'
    return Paragraph(f'<font color="{hex_color}">{filled}</font>{empty}', S['td'])

# ── 封面 ─────────────────────────────────────────────────────
def build_cover():
    elems = []

    # 顶部色块
    cover_table = Table(
        [[Paragraph('Gemini 渠道质量测试报告', S['title']),
          Paragraph('Gemini Channel Quality Test Report', S['subtitle'])]],
        colWidths=[16*cm],
        style=TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), C_DARK_BLUE),
            ('TOPPADDING', (0,0), (-1,-1), 30),
            ('BOTTOMPADDING', (0,0), (-1,-1), 30),
            ('LEFTPADDING', (0,0), (-1,-1), 20),
            ('RIGHTPADDING', (0,0), (-1,-1), 20),
        ])
    )
    elems.append(cover_table)
    elems.append(sp(0.8))

    # 基本信息卡片
    info_data = [
        [Paragraph('测试地址', S['th']), Paragraph('http://51.81.184.93:32691/', S['td_l'])],
        [Paragraph('令牌分组', S['th']), Paragraph('gemini-ssvip / gemini-image / Gemini-T1', S['td_l'])],
        [Paragraph('测试时间', S['th']), Paragraph('2026-03-28', S['td_l'])],
        [Paragraph('测试范围', S['th']), Paragraph('Gemini 2.0 / 2.5 / 3.1 系列全模型', S['td_l'])],
        [Paragraph('测试项目', S['th']), Paragraph('可用性 · 延迟 · 并发 · 流式 · 视觉 · 工具调用 · Embedding · 缓存', S['td_l'])],
    ]
    info_table = Table(info_data, colWidths=[3.5*cm, 12.5*cm],
        style=TableStyle([
            ('BACKGROUND', (0,0), (0,-1), C_MID_BLUE),
            ('BACKGROUND', (1,0), (1,-1), C_WHITE),
            ('GRID', (0,0), (-1,-1), 0.5, C_GRAY_BORDER),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
        ])
    )
    elems.append(info_table)
    elems.append(sp(0.8))

    # 总体评分卡
    score_data = [
        [Paragraph('评估维度', S['th']),
         Paragraph('评分', S['th']),
         Paragraph('说明', S['th'])],
        [p('整体可用性'), rating_bar(4), p('核心模型全部可用，部分 preview 版本缺失渠道')],
        [p('响应延迟'), rating_bar(4), p('Flash 系列 ~1.5s，Pro 系列 3~10s（含 thinking）')],
        [p('并发稳定性'), rating_bar(5), p('20并发零失败，墙钟时间几乎不随并发增加')],
        [p('功能完整性'), rating_bar(5), p('流式/工具调用/视觉/JSON/Embedding 全部通过')],
        [p('缓存命中率'), rating_bar(2), p('当前 prompt 较短，未触发隐式缓存（正常）')],
    ]
    score_table = Table(score_data, colWidths=[4*cm, 3.5*cm, 8.5*cm],
        style=TableStyle([
            ('BACKGROUND', (0,0), (-1,0), C_DARK_BLUE),
            ('BACKGROUND', (0,1), (-1,-1), C_WHITE),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [C_WHITE, C_GRAY_BG]),
            ('GRID', (0,0), (-1,-1), 0.4, C_GRAY_BORDER),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
        ])
    )
    elems.append(score_table)
    elems.append(PageBreak())
    return elems

# ── 第1节：模型可用性 ─────────────────────────────────────────
def build_section1():
    elems = []
    elems.append(section_title('模型可用性测试', '1'))
    elems.append(sp(0.3))
    elems.append(p('对 gemini 分组令牌下所有已知模型进行可用性探测，结果如下：'))
    elems.append(sp(0.3))

    # Gemini 2.x 系列
    elems.append(p('▍ Gemini 2.x 系列', 'h2'))
    rows_2x = [
        [p('gemini-2.0-flash', 'td_l'),      status_cell('ok'),   p('主力模型，响应正常', 'td_l'),        p('~960ms', 'td')],
        [p('gemini-2.0-flash-001', 'td_l'),   status_cell('fail'), p('该分组无此渠道', 'td_l'),            p('—', 'td')],
        [p('gemini-2.0-flash-exp', 'td_l'),   status_cell('fail'), p('该分组无此渠道', 'td_l'),            p('—', 'td')],
        [p('gemini-2.0-flash-lite', 'td_l'),  status_cell('fail'), p('该分组无此渠道', 'td_l'),            p('—', 'td')],
        [p('gemini-2.0-flash-lite-001','td_l'),status_cell('fail'),p('Gemini-T1 分组无渠道', 'td_l'),      p('—', 'td')],
        [p('gemini-2.0-pro-exp', 'td_l'),     status_cell('fail'), p('该分组无此渠道', 'td_l'),            p('—', 'td')],
        [p('gemini-2.5-flash', 'td_l'),       status_cell('ok'),   p('支持 Thinking 推理', 'td_l'),        p('~1.2s', 'td')],
        [p('gemini-2.5-flash-nothinking','td_l'),status_cell('ok'),p('无思考模式，响应快', 'td_l'),         p('~1.0s', 'td')],
        [p('gemini-2.5-pro', 'td_l'),         status_cell('ok'),   p('高级推理，含 thinking', 'td_l'),     p('2.7s', 'td')],
        [p('gemini-2.5-pro-preview-03-25','td_l'),status_cell('fail'),p('该分组无此渠道','td_l'),          p('—', 'td')],
        [p('gemini-flash-latest', 'td_l'),    status_cell('ok'),   p('别名路由', 'td_l'),                  p('~1.0s', 'td')],
        [p('gemini-pro-latest', 'td_l'),      status_cell('ok'),   p('别名路由', 'td_l'),                  p('~1.0s', 'td')],
        [p('gemini-flash-lite-latest', 'td_l'),status_cell('ok'),  p('Lite 版本', 'td_l'),                 p('~1.0s', 'td')],
        [p('gemini-1.5-pro', 'td_l'),         status_cell('fail'), p('该分组无此渠道', 'td_l'),            p('—', 'td')],
        [p('gemini-1.5-flash', 'td_l'),       status_cell('fail'), p('该分组无此渠道', 'td_l'),            p('—', 'td')],
    ]
    elems.append(make_table(
        ['模型名称', '状态', '备注', '基准延迟'],
        rows_2x, [5.5*cm, 2*cm, 6.5*cm, 2*cm]
    ))
    elems.append(sp(0.4))

    # Gemini 3.1 系列
    elems.append(p('▍ Gemini 3.1 系列（2026年2月~3月发布）', 'h2'))
    rows_31 = [
        [p('gemini-3.1-pro-preview', 'td_l'),           status_cell('ok'),   p('高推理能力，延迟波动大', 'td_l'),       p('4~141s', 'td')],
        [p('gemini-3.1-pro-preview-customtools','td_l'), status_cell('ok'),   p('工具调用优化版', 'td_l'),              p('3~6s', 'td')],
        [p('gemini-3.1-pro-preview-high', 'td_l'),       status_cell('ok'),   p('高 thinking budget', 'td_l'),          p('长', 'td')],
        [p('gemini-3.1-pro-preview-low', 'td_l'),        status_cell('ok'),   p('低 thinking budget', 'td_l'),          p('4~8s', 'td')],
        [p('gemini-3.1-flash-lite-preview', 'td_l'),     status_cell('ok'),   p('最轻量，高并发首选', 'td_l'),           p('~1.4s', 'td')],
        [p('gemini-3.1-flash-image-preview', 'td_l'),    status_cell('ok'),   p('多模态图像理解', 'td_l'),              p('~1.7s', 'td')],
        [p('gemini-3.1-flash-preview', 'td_l'),          status_cell('fail'), p('该分组无此渠道', 'td_l'),              p('—', 'td')],
        [p('gemini-3.1-flash-live-preview', 'td_l'),     status_cell('fail'), p('该分组无此渠道（实时语音）', 'td_l'),  p('—', 'td')],
        [p('gemini-3.1-pro-preview-medium', 'td_l'),     status_cell('fail'), p('gemini-image 分组无渠道', 'td_l'),     p('—', 'td')],
    ]
    elems.append(make_table(
        ['模型名称', '状态', '备注', '基准延迟'],
        rows_31, [5.5*cm, 2*cm, 6.5*cm, 2*cm]
    ))
    elems.append(sp(0.3))

    # Embedding & 其他
    elems.append(p('▍ Embedding & 其他', 'h2'))
    rows_emb = [
        [p('gemini-embedding-001', 'td_l'), status_cell('ok'),   p('3072维向量，正常', 'td_l'),    p('~1.2s', 'td')],
        [p('text-embedding-004', 'td_l'),   status_cell('fail'), p('该分组无此渠道', 'td_l'),      p('—', 'td')],
        [p('imagen-3.0-generate-002','td_l'),status_cell('ok'),  p('图像生成（列表可见）', 'td_l'), p('未测', 'td')],
    ]
    elems.append(make_table(
        ['模型名称', '状态', '备注', '基准延迟'],
        rows_emb, [5.5*cm, 2*cm, 6.5*cm, 2*cm]
    ))
    elems.append(PageBreak())
    return elems

# ── 第2节：功能测试 ───────────────────────────────────────────
def build_section2():
    elems = []
    elems.append(section_title('功能完整性测试', '2'))
    elems.append(sp(0.3))

    func_rows = [
        [p('非流式对话', 'td_l'),     status_cell('ok'),
         p('gemini-2.0-flash / 2.5-pro 均正常，finish_reason=stop', 'td_l')],
        [p('流式对话 (SSE)', 'td_l'), status_cell('ok'),
         p('SSE 格式正确，chunk 分片正常，首 token 延迟 <1s', 'td_l')],
        [p('多轮对话记忆', 'td_l'),   status_cell('ok'),
         p('正确记住上下文（用户名 Alice），messages 历史传递正常', 'td_l')],
        [p('Function Calling', 'td_l'), status_cell('ok'),
         p('正确触发 get_weather 工具，参数 {"location":"Beijing"} 准确', 'td_l')],
        [p('JSON 输出模式', 'td_l'),  status_cell('ok'),
         p('response_format: json_object 返回合法 JSON，字段完整', 'td_l')],
        [p('视觉/图像理解', 'td_l'),  status_cell('ok'),
         p('base64 PNG 输入，正确识别颜色（Red/Blue），image_tokens 正常计费', 'td_l')],
        [p('Embedding', 'td_l'),       status_cell('ok'),
         p('gemini-embedding-001 返回 3072 维向量，数值正常', 'td_l')],
        [p('Thinking 推理', 'td_l'),   status_cell('ok'),
         p('gemini-2.5-flash/pro 及 3.1-pro-preview reasoning_tokens 正常计费', 'td_l')],
        [p('3.1-customtools 工具调用','td_l'), status_cell('ok'),
         p('search_web 工具正确触发，reasoning_tokens=77，响应 3.5s', 'td_l')],
        [p('3.1-flash-lite 流式', 'td_l'), status_cell('ok'),
         p('SSE 分片流畅，无 reasoning_tokens（非思考模型），2s 完成', 'td_l')],
        [p('外部 URL 图片', 'td_l'),   status_cell('fail'),
         p('403 下载失败（服务端下载 Wikipedia 图片被拒），需用 base64', 'td_l')],
    ]
    elems.append(make_table(
        ['测试项目', '结果', '详情'],
        func_rows, [3.5*cm, 1.8*cm, 10.7*cm]
    ))
    elems.append(sp(0.5))

    # Token 计费字段说明
    elems.append(p('▍ Token 计费字段说明', 'h2'))
    token_rows = [
        [p('prompt_tokens_details.cached_tokens', 'code'),   p('缓存命中的 prompt token 数，当前测试均为 0')],
        [p('completion_tokens_details.reasoning_tokens', 'code'), p('Thinking 模型的思考 token 数（2.5/3.1 Pro 系列有值）')],
        [p('prompt_tokens_details.image_tokens', 'code'),    p('图片占用的 token 数（100×100 PNG = 272 tokens）')],
        [p('prompt_tokens_details.text_tokens', 'code'),     p('纯文本 prompt token 数')],
    ]
    elems.append(make_table(
        ['字段', '说明'],
        token_rows, [6.5*cm, 9.5*cm]
    ))
    elems.append(PageBreak())
    return elems

# ── 第3节：延迟性能 ───────────────────────────────────────────
def build_section3():
    elems = []
    elems.append(section_title('延迟性能测试', '3'))
    elems.append(sp(0.3))

    elems.append(p('▍ Gemini 2.x 系列 — 10次连续请求延迟（gemini-2.0-flash）', 'h2'))
    lat_rows = [
        [p('#1'), p('993ms'), p('#6'), p('917ms')],
        [p('#2'), p('921ms'), p('#7'), p('996ms')],
        [p('#3'), p('996ms'), p('#8'), p('1003ms')],
        [p('#4'), p('994ms'), p('#9'), p('1057ms')],
        [p('#5'), p('942ms'), p('#10'), p('891ms')],
    ]
    lat_table = Table(
        [[Paragraph('请求', S['th']), Paragraph('延迟', S['th']),
          Paragraph('请求', S['th']), Paragraph('延迟', S['th'])]] + lat_rows,
        colWidths=[2*cm, 3*cm, 2*cm, 3*cm],
        style=TableStyle([
            ('BACKGROUND', (0,0), (-1,0), C_DARK_BLUE),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [C_WHITE, C_GRAY_BG]),
            ('GRID', (0,0), (-1,-1), 0.4, C_GRAY_BORDER),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ])
    )
    stat_table = Table(
        [[Paragraph('统计项', S['th']), Paragraph('数值', S['th']),
          Paragraph('统计项', S['th']), Paragraph('数值', S['th'])],
         [p('最小延迟'), p('891ms'), p('最大延迟'), p('1057ms')],
         [p('平均延迟'), p('~961ms'), p('标准差'), p('~50ms')],
        ],
        colWidths=[2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm],
        style=TableStyle([
            ('BACKGROUND', (0,0), (-1,0), C_MID_BLUE),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [C_WHITE, C_GRAY_BG]),
            ('GRID', (0,0), (-1,-1), 0.4, C_GRAY_BORDER),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ])
    )
    combined = Table([[lat_table, Spacer(0.3*cm, 1), stat_table]],
        colWidths=[10.5*cm, 0.3*cm, 10.5*cm])
    elems.append(Table([[lat_table, stat_table]], colWidths=[10.5*cm, 9.5*cm],
        style=TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'), ('LEFTPADDING',(1,0),(1,0),12)])))
    elems.append(sp(0.5))

    elems.append(p('▍ Gemini 3.1 系列 — 单请求基准延迟（3次采样）', 'h2'))
    lat31_rows = [
        [p('gemini-3.1-flash-lite-preview', 'td_l'), p('1350ms'), p('1405ms'), p('1487ms'), p('1414ms'), Paragraph('极稳定', S['ok'])],
        [p('gemini-3.1-flash-image-preview', 'td_l'), p('2137ms'), p('1548ms'), p('1747ms'), p('1811ms'), Paragraph('稳定', S['ok'])],
        [p('gemini-3.1-pro-preview-customtools', 'td_l'), p('3590ms'), p('5470ms'), p('3114ms'), p('4058ms'), Paragraph('一般', S['warn'])],
        [p('gemini-3.1-pro-preview-low', 'td_l'), p('4092ms'), p('5741ms'), p('7684ms'), p('5839ms'), Paragraph('波动', S['warn'])],
        [p('gemini-3.1-pro-preview', 'td_l'), p('7397ms'), p('141275ms'), p('4290ms'), p('—', 'td'), Paragraph('不稳定', S['fail'])],
    ]
    elems.append(make_table(
        ['模型', '第1次', '第2次', '第3次', '均值', '稳定性'],
        lat31_rows, [5*cm, 2*cm, 2*cm, 2*cm, 2*cm, 3*cm]
    ))
    elems.append(sp(0.3))
    elems.append(p('⚠ gemini-3.1-pro-preview 第2次请求耗时 141s，原因为 thinking token 超量消耗，'
                   '生产环境建议使用流式接口并设置合理的 max_tokens 上限。', 'note'))
    elems.append(PageBreak())
    return elems

# ── 第4节：并发性能 ───────────────────────────────────────────
def build_section4():
    elems = []
    elems.append(section_title('并发性能测试', '4'))
    elems.append(sp(0.3))
    elems.append(p('所有并发测试均使用 Python ThreadPoolExecutor 同时发起请求，测试消息为 "What is 1+1?"，max_tokens=30。'))
    elems.append(sp(0.3))

    # 2.0-flash 并发（历史数据）
    elems.append(p('▍ gemini-2.0-flash — 并发测试（5并发）', 'h2'))
    elems.append(p('5个并发请求总墙钟时间：1103ms，所有请求均成功返回正确答案。'))
    elems.append(sp(0.3))

    # 3.1 Flash Lite
    elems.append(p('▍ gemini-3.1-flash-lite-preview — 并发测试', 'h2'))
    conc_lite_rows = [
        [p('1'),  p('100%'), p('1634ms'), p('1633ms'), p('1633ms'), p('1633ms'), p('1633ms')],
        [p('5'),  p('100%'), p('1888ms'), p('1554ms'), p('1344ms'), p('1887ms'), p('1637ms')],
        [p('10'), p('100%'), p('1831ms'), p('1394ms'), p('1286ms'), p('1829ms'), p('1432ms')],
        [p('20'), p('100%'), p('1926ms'), p('1526ms'), p('1307ms'), p('1922ms'), p('1749ms')],
    ]
    elems.append(make_table(
        ['并发数', '成功率', '墙钟时间', 'avg', 'min', 'max', 'p95'],
        conc_lite_rows, [1.5*cm, 1.8*cm, 2.5*cm, 2*cm, 2*cm, 2*cm, 2.2*cm]
    ))
    elems.append(sp(0.2))
    elems.append(p('✅ 20并发零失败，墙钟时间仅 1.9s，与单请求几乎持平，并发扩展性极佳。', 'note'))
    elems.append(sp(0.4))

    # 3.1 Flash Image
    elems.append(p('▍ gemini-3.1-flash-image-preview — 并发测试', 'h2'))
    conc_img_rows = [
        [p('1'),  p('100%'), p('1802ms'), p('1802ms'), p('1802ms'), p('1802ms'), p('1802ms')],
        [p('5'),  p('100%'), p('1861ms'), p('1569ms'), p('1439ms'), p('1860ms'), p('1594ms')],
        [p('10'), p('100%'), p('1788ms'), p('1575ms'), p('1469ms'), p('1785ms'), p('1703ms')],
    ]
    elems.append(make_table(
        ['并发数', '成功率', '墙钟时间', 'avg', 'min', 'max', 'p95'],
        conc_img_rows, [1.5*cm, 1.8*cm, 2.5*cm, 2*cm, 2*cm, 2*cm, 2.2*cm]
    ))
    elems.append(sp(0.2))
    elems.append(p('✅ 10并发全部成功，延迟稳定在 1.5~1.8s，多模态处理能力强。', 'note'))
    elems.append(sp(0.4))

    # 3.1 Pro customtools
    elems.append(p('▍ gemini-3.1-pro-preview-customtools — 并发测试', 'h2'))
    conc_pro_rows = [
        [p('1'), p('100%'), p('9802ms'), p('9801ms'), p('9801ms'), p('9801ms'), p('9801ms')],
        [p('3'), p('100%'), p('2888ms'), p('2789ms'), p('2666ms'), p('2888ms'), p('2814ms')],
        [p('5'), p('100%'), p('4183ms'), p('3404ms'), p('2560ms'), p('4182ms'), p('4095ms')],
    ]
    elems.append(make_table(
        ['并发数', '成功率', '墙钟时间', 'avg', 'min', 'max', 'p95'],
        conc_pro_rows, [1.5*cm, 1.8*cm, 2.5*cm, 2*cm, 2*cm, 2*cm, 2.2*cm]
    ))
    elems.append(sp(0.2))
    elems.append(p('⚠ 单请求偶发 ~10s 高延迟（thinking 时间），并发 3~5 时反而更快（约 3s），'
                   '说明上游有并发加速效果，零失败。', 'note'))
    elems.append(sp(0.4))

    # 综合对比
    elems.append(p('▍ 并发性能综合对比', 'h2'))
    compare_rows = [
        [p('gemini-2.0-flash', 'td_l'),               p('5'),  p('100%'), p('1103ms'), Paragraph('⭐⭐⭐⭐⭐', S['ok'])],
        [p('gemini-3.1-flash-lite-preview', 'td_l'),  p('20'), p('100%'), p('1926ms'), Paragraph('⭐⭐⭐⭐⭐', S['ok'])],
        [p('gemini-3.1-flash-image-preview', 'td_l'), p('10'), p('100%'), p('1788ms'), Paragraph('⭐⭐⭐⭐⭐', S['ok'])],
        [p('gemini-3.1-pro-preview-customtools','td_l'), p('5'), p('100%'), p('4183ms'), Paragraph('⭐⭐⭐⭐', S['ok'])],
        [p('gemini-3.1-pro-preview', 'td_l'),         p('—'), p('—'),    p('不稳定'),  Paragraph('⭐⭐', S['warn'])],
    ]
    elems.append(make_table(
        ['模型', '最大测试并发', '成功率', '墙钟时间', '并发评级'],
        compare_rows, [5.5*cm, 2.5*cm, 2*cm, 2.5*cm, 3.5*cm]
    ))
    elems.append(PageBreak())
    return elems

# ── 第5节：缓存命中率 ─────────────────────────────────────────
def build_section5():
    elems = []
    elems.append(section_title('缓存命中率测试', '5'))
    elems.append(sp(0.3))

    elems.append(p('对 gemini-2.0-flash 使用相同的大 prompt（约 979 tokens）连续发起 3 次请求，观察 cached_tokens 字段。'))
    elems.append(sp(0.3))

    cache_rows = [
        [p('第1次'), p('979'), p('0'), p('0%'), p('1.3s'), Paragraph('未命中', S['fail'])],
        [p('第2次'), p('979'), p('0'), p('0%'), p('1.5s'), Paragraph('未命中', S['fail'])],
        [p('第3次'), p('979'), p('0'), p('0%'), p('1.6s'), Paragraph('未命中', S['fail'])],
    ]
    elems.append(make_table(
        ['请求次序', 'prompt_tokens', 'cached_tokens', '命中率', '响应时间', '状态'],
        cache_rows, [2*cm, 2.8*cm, 2.8*cm, 2*cm, 2.2*cm, 2.2*cm]
    ))
    elems.append(sp(0.4))

    elems.append(p('▍ 原因分析', 'h2'))
    analysis = [
        '1. Gemini 隐式缓存（Implicit Caching）触发条件：',
        '   • gemini-2.0-flash：prompt 需超过 <b>32,768 tokens</b>',
        '   • gemini-1.5 系列：prompt 需超过 <b>1,024 tokens</b>（该分组不可用）',
        '2. 本次测试 prompt 仅约 979 tokens，远未达到 gemini-2.0-flash 的缓存阈值',
        '3. 缓存命中率为 0% 属于<b>正常现象</b>，并非渠道问题',
        '4. 若需验证缓存功能，建议构造超过 32K tokens 的超长 system prompt 重复请求',
        '5. 或使用 Gemini 原生 API 的显式缓存（Explicit Context Caching）接口',
    ]
    for line in analysis:
        elems.append(p(line))
        elems.append(sp(0.1))

    elems.append(sp(0.3))
    elems.append(Table(
        [[Paragraph('💡 建议：生产环境中若需利用缓存降低成本，应将固定的 system prompt / 文档内容'
                    '设计为超过 32K tokens，或采用 Gemini API 显式缓存接口预先创建缓存对象。', S['note'])]],
        colWidths=[16*cm],
        style=TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), C_YELLOW_BG),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#fbbf24')),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING', (0,0), (-1,-1), 12),
        ])
    ))
    elems.append(PageBreak())
    return elems

# ── 第6节：总结与建议 ─────────────────────────────────────────
def build_section6():
    elems = []
    elems.append(section_title('总结与建议', '6'))
    elems.append(sp(0.3))

    elems.append(p('▍ 整体评估', 'h2'))
    summary_rows = [
        [p('整体可用性', 'td_l'),  rating_bar(4), p('核心模型全部可用；gemini-1.5 系列、部分 3.1 preview 版本缺失渠道', 'td_l')],
        [p('响应延迟', 'td_l'),    rating_bar(4), p('Flash 系列 ~1.4s，Pro 系列 3~10s（含 thinking），偶发超长', 'td_l')],
        [p('并发稳定性', 'td_l'),  rating_bar(5), p('20并发零失败，墙钟时间几乎不随并发增加，表现优秀', 'td_l')],
        [p('功能完整性', 'td_l'),  rating_bar(5), p('流式/工具调用/视觉/JSON/Embedding/Thinking 全部通过', 'td_l')],
        [p('缓存命中率', 'td_l'),  rating_bar(2), p('当前 prompt 较短未触发，属正常；需超 32K tokens 才可触发', 'td_l')],
        [p('Token 计费', 'td_l'),  rating_bar(4), p('字段完整，reasoning_tokens 正确计费，image_tokens 正常', 'td_l')],
    ]
    elems.append(make_table(
        ['评估维度', '评分（5星）', '说明'],
        summary_rows, [3.5*cm, 3*cm, 9.5*cm]
    ))
    elems.append(sp(0.5))

    elems.append(p('▍ 问题清单', 'h2'))
    issue_rows = [
        [p('P1', 'td_l'), Paragraph('中', S['warn']),
         p('gemini-3.1-pro-preview 延迟极不稳定（4s~141s），thinking token 无上限', 'td_l'),
         p('流式接口 + 合理 max_tokens', 'td_l')],
        [p('P2', 'td_l'), Paragraph('低', S['ok']),
         p('gemini-1.5 系列在 gemini-ssvip 分组下不可用', 'td_l'),
         p('补充 gemini-1.5 渠道或确认是否需要', 'td_l')],
        [p('P3', 'td_l'), Paragraph('低', S['ok']),
         p('gemini-3.1-flash-preview / live-preview 不可用', 'td_l'),
         p('补充对应渠道配置', 'td_l')],
        [p('P4', 'td_l'), Paragraph('低', S['ok']),
         p('外部 URL 图片下载失败（403）', 'td_l'),
         p('使用 base64 编码传递图片', 'td_l')],
        [p('P5', 'td_l'), Paragraph('信息', S['ok']),
         p('缓存命中率 0%（prompt 未达阈值，非缺陷）', 'td_l'),
         p('无需处理，属正常行为', 'td_l')],
    ]
    elems.append(make_table(
        ['编号', '优先级', '问题描述', '建议处理'],
        issue_rows, [1.2*cm, 1.5*cm, 7.5*cm, 5.8*cm]
    ))
    elems.append(sp(0.5))

    elems.append(p('▍ 使用建议', 'h2'))
    advice = [
        ('高吞吐/低成本场景', 'gemini-3.1-flash-lite-preview', '~1.4s，20并发零失败，成本最低'),
        ('多模态图文理解',     'gemini-3.1-flash-image-preview', '~1.7s，视觉能力强，并发好'),
        ('工具调用/Agent',    'gemini-3.1-pro-preview-customtools', '3~6s，工具调用优化，推荐流式'),
        ('复杂推理/分析',     'gemini-2.5-pro / gemini-3.1-pro-preview', '含 thinking，建议流式+大 max_tokens'),
        ('向量检索',          'gemini-embedding-001', '3072维，延迟~1.2s'),
        ('快速原型/通用',     'gemini-2.0-flash', '~960ms，稳定，功能全面'),
    ]
    adv_rows = [[p(a[0], 'td_l'), p(a[1], 'code'), p(a[2], 'td_l')] for a in advice]
    elems.append(make_table(
        ['使用场景', '推荐模型', '说明'],
        adv_rows, [3.5*cm, 5.5*cm, 7*cm]
    ))

    elems.append(sp(0.6))
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    elems.append(Table(
        [[Paragraph(f'报告生成时间：{now}　|　测试执行人：系统自动化测试', S['small'])]],
        colWidths=[16*cm],
        style=TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), C_DARK_BLUE),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING', (0,0), (-1,-1), 12),
        ])
    ))
    return elems

# ── 页眉页脚 ──────────────────────────────────────────────────
def on_page(canvas, doc):
    canvas.saveState()
    w, h = A4
    # 页眉
    canvas.setFillColor(C_DARK_BLUE)
    canvas.rect(0, h-1.2*cm, w, 1.2*cm, fill=1, stroke=0)
    canvas.setFont('MSYH', 8)
    canvas.setFillColor(C_WHITE)
    canvas.drawString(1.5*cm, h-0.8*cm, 'Gemini 渠道质量测试报告  |  http://51.81.184.93:32691/')
    canvas.drawRightString(w-1.5*cm, h-0.8*cm, '2026-03-28')
    # 页脚
    canvas.setFillColor(C_GRAY_BORDER)
    canvas.rect(0, 0, w, 0.8*cm, fill=1, stroke=0)
    canvas.setFont('MSYH', 7.5)
    canvas.setFillColor(C_SUBTEXT)
    canvas.drawCentredString(w/2, 0.28*cm, f'第 {doc.page} 页')
    canvas.restoreState()

# ── 主函数 ────────────────────────────────────────────────────
def build_pdf():
    out = r'e:\new-api\scripts\gemini_quality_test_report.pdf'
    doc = SimpleDocTemplate(
        out, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.8*cm, bottomMargin=1.2*cm,
        title='Gemini 渠道质量测试报告',
        author='New-API 自动化测试',
        subject='Gemini Channel Quality Test Report 2026-03-28',
    )

    story = []
    story += build_cover()
    story += build_section1()
    story += build_section2()
    story += build_section3()
    story += build_section4()
    story += build_section5()
    story += build_section6()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f'PDF 已生成: {out}')
    return out

if __name__ == '__main__':
    build_pdf()
