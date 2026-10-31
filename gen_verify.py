from openpyxl import Workbook

wb = Workbook()
ws = wb.active
ws.title = "验证"
ws.append(["名称", "数值"])
for row in [("项目A", 42), ("项目B", 87), ("项目C", 156)]:
    ws.append(row)
wb.save("/ws/verify.xlsx")
print("saved verify.xlsx")