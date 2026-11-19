"""Propuesta comercial B2B con tabla paginada y valores de la cotización emitida."""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor('#172a35')
MUTED = colors.HexColor('#667982')
TEAL = colors.HexColor('#0f766e')
PALE = colors.HexColor('#edf7f5')
LINE = colors.HexColor('#dce8e7')


def generar_cotizacion_pdf(cotizacion):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm, title=f'Cotización {cotizacion.codigo_cotizacion}',
                            author='MaxiConecta')
    width = doc.width
    normal = ParagraphStyle('body', fontName='Helvetica', fontSize=9, leading=13, textColor=INK, splitLongWords=True)
    small = ParagraphStyle('small', parent=normal, fontSize=8, leading=11, textColor=MUTED)
    bold = ParagraphStyle('bold', parent=normal, fontName='Helvetica-Bold')
    heading = ParagraphStyle('heading', parent=normal, fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=TEAL)
    title = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=23, leading=27, textColor=INK)
    right = ParagraphStyle('right', parent=normal, alignment=TA_RIGHT)
    right_bold = ParagraphStyle('right_bold', parent=bold, alignment=TA_RIGHT)
    column = ParagraphStyle('column', parent=small, fontName='Helvetica-Bold', textColor=colors.white, fontSize=8)
    column_right = ParagraphStyle('column_right', parent=column, alignment=TA_RIGHT)

    def p(value, style=normal):
        return Paragraph(escape(str(value if value is not None else '')), style)

    def money(value):
        return f'BOB {Decimal(str(value)):,.2f}'

    def fecha(value):
        return value.strftime('%d/%m/%Y')

    def page(canvas, document):
        canvas.saveState()
        w, _ = A4
        canvas.setStrokeColor(LINE)
        canvas.line(20*mm, 15*mm, w-20*mm, 15*mm)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(20*mm, 10*mm, 'MaxiConecta  |  Propuesta comercial corporativa')
        canvas.drawRightString(w-20*mm, 10*mm, f'Página {document.page}')
        canvas.restoreState()

    fecha_emision = cotizacion.created_at or datetime.utcnow()
    story = []
    header = Table([[p('MaxiConecta', ParagraphStyle('brand', parent=bold, fontSize=15, textColor=TEAL)),
                     p('COTIZACIÓN COMERCIAL', ParagraphStyle('tag', parent=small, alignment=TA_RIGHT, fontName='Helvetica-Bold'))]],
                   colWidths=[width/2, width/2])
    header.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),0),
                                ('RIGHTPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),9),
                                ('LINEBELOW',(0,0),(-1,-1),1.2,TEAL)]))
    story.extend([header, Spacer(1, 16*mm), p('Cotización', title), Spacer(1, 2*mm),
                  p(cotizacion.codigo_cotizacion, ParagraphStyle('code', parent=normal, fontName='Helvetica-Bold', fontSize=11, textColor=TEAL)),
                  Spacer(1, 9*mm)])

    details = Table([
        [p('PREPARADA PARA', small), p('FECHA DE EMISIÓN', small), p('VÁLIDA HASTA', small)],
        [p(cotizacion.razon_social or cotizacion.nombre_cliente, bold), p(fecha(fecha_emision), bold), p(fecha(cotizacion.vigencia_hasta), bold)],
        [p(f'NIT: {cotizacion.nit_ci}', small), p(f'Vigencia: {cotizacion.vigencia_dias} días', small), p('', small)],
        [p(f'Contacto: {cotizacion.nombre_cliente}', small), '', ''],
    ], colWidths=[width*.50, width*.25, width*.25])
    details.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),11),('RIGHTPADDING',(0,0),(-1,-1),9),
        ('TOPPADDING',(0,0),(-1,0),10),('BOTTOMPADDING',(0,-1),(-1,-1),10),
        ('TOPPADDING',(0,1),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-2),2)]))
    story.extend([details, Spacer(1, 11*mm), p('Detalle de productos', heading), Spacer(1, 3*mm)])

    rows = [[p('PRODUCTO / SKU', column), p('CANT.', column_right), p('PRECIO UNIT.', column_right), p('IMPORTE', column_right)]]
    for item in cotizacion.items:
        product = Paragraph(f'{escape(str(item.nombre_producto))}<br/><font color="#667982" size="8">SKU: {escape(str(item.sku))}</font>', normal)
        rows.append([product, p(item.cantidad, right), p(money(item.precio_unitario), right), p(money(item.total_linea), right_bold)])
    table = Table(rows, colWidths=[width*.43, width*.10, width*.23, width*.24], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),TEAL),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
        ('TOPPADDING',(0,0),(-1,0),8),('BOTTOMPADDING',(0,0),(-1,0),8),
        ('TOPPADDING',(0,1),(-1,-1),9),('BOTTOMPADDING',(0,1),(-1,-1),9),
        ('LINEBELOW',(0,1),(-1,-1),.45,LINE)]))
    story.append(table)

    percentage = format(Decimal(str(cotizacion.descuento_porcentaje)).normalize(), 'f')
    summary = Table([
        [p('Subtotal', small), p(money(cotizacion.subtotal), right)],
        [p(f'Descuento por volumen ({percentage}%)', small), p(f'- {money(cotizacion.descuento_monto)}', right)],
        [p('TOTAL COTIZADO', ParagraphStyle('total_label', parent=bold, textColor=colors.white, fontSize=9)),
         p(money(cotizacion.total), ParagraphStyle('total_value', parent=right_bold, textColor=colors.white, fontSize=12))],
    ], colWidths=[width*.33, width*.27], hAlign='RIGHT')
    summary.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),7),
        ('BOTTOMPADDING',(0,0),(-1,-1),7),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
        ('BACKGROUND',(0,-1),(-1,-1),TEAL)]))
    notes = [Spacer(1, 8*mm), summary, Spacer(1, 10*mm), p('Condiciones comerciales', heading), Spacer(1, 2*mm),
             p('Esta cotización es válida hasta la fecha indicada y está sujeta a disponibilidad.', small),
             p('Los precios se expresan en bolivianos (BOB).', small)]
    story.append(KeepTogether(notes))
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return buffer.getvalue()
