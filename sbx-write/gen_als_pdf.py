#!/usr/bin/env python3
"""生成《ALS 测试》PDF：标题 + 正文三行 hello world"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))

OUT = '/ws/demo-tc4yvw3te/sbx-write/als-test.pdf'
c = canvas.Canvas(OUT, pagesize=A4)
w, h = A4

# 标题
c.setFont('STSong-Light', 24)
c.drawCentredString(w / 2, h - 60 * mm, 'ALS 测试')

# 正文三行
c.setFont('STSong-Light', 14)
for i in range(3):
    c.drawString(30 * mm, h - (85 + i * 12) * mm, 'hello world')

c.showPage()
c.save()
print('OK', OUT)
