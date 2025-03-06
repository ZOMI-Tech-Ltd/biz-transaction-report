from decimal import Decimal
import mysql.connector
import os
from dotenv import load_dotenv

class TaxCalculator:
    BC_GST_RATE = Decimal("0.05")
    BC_SodaTax_RATE = Decimal("0.07")
    BC_LiquorTax_RATE = Decimal("0.10")

    def __init__(self):
        load_dotenv()
        self.connection = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST'),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASS'),
            database=os.getenv('MYSQL_DB')
        )
        self.cursor = self.connection.cursor(dictionary=True)

    def calculate_taxes(self, order_ids):
        """根据订单ID列表计算GST_total与PST_total"""
        if not order_ids:
            return {"GST_total": Decimal("0.00"), "PST_total": Decimal("0.00")}
        format_strings = ','.join(['%s'] * len(order_ids))
        query = f"""
            SELECT odt.order_id, odt.dish_id, odt.system_tax_id, od.amount
            FROM order_dish_tax odt
            JOIN order_dish od ON odt.order_id = od.order_id AND odt.dish_id = od.dish_id
            WHERE odt.order_id IN ({format_strings})
        """
        self.cursor.execute(query, tuple(order_ids))
        rows = self.cursor.fetchall()

        GST_total = Decimal("0")
        PST_total = Decimal("0")
        for row in rows:
            amount = Decimal(row["amount"])
            system_tax_id = row["system_tax_id"]
            if system_tax_id == 1:
                GST_total += amount * self.BC_GST_RATE
            elif system_tax_id == 2:
                PST_total += amount * self.BC_LiquorTax_RATE
            elif system_tax_id == 3:
                PST_total += amount * self.BC_SodaTax_RATE
        return {"GST_total": GST_total, "PST_total": PST_total}

    def close(self):
        self.cursor.close()
        self.connection.close()


if __name__ == "__main__":
    # 可通过命令行传入订单ID列表以测试
    import sys
    order_ids = sys.argv[1:]
    tc = TaxCalculator()
    totals = tc.calculate_taxes(order_ids)
    print("GST_total:", totals["GST_total"])
    print("PST_total:", totals["PST_total"])
    tc.close()


